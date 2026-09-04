from contextlib import contextmanager
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli._common import _app, _exit_unless_ok, cli, console
from linkedin.services.automation_service import publish_unreviewed
from linkedin.services.contact_service import (
    import_scraped_profile,
    import_search_results,
)
from linkedin.services.resume_service import (
    ResumeRepoError,
    match_variants,
    resolve_pdf,
)


class _SessionUnavailable(SystemExit):
    pass


def _pause_for_manual_login(page) -> bool:
    """Hand the window to the person: automatic login failed, they finish it."""
    console.print(
        "[yellow]Automatic login failed — complete the login (and any checkpoint) in the browser window.[/yellow]\n"
        "[dim]No credentials are stored unless you ran `linkedin-cli automate setup`; logging in by hand here is fine "
        "and the session is saved afterwards.[/dim]"
    )
    click.pause("Press any key once you are logged in...")
    return page.is_logged_in()


@contextmanager
def _open_session(headless: bool = False, dry_run: bool = False):
    """A logged-in LinkedInSession, or a clear exit. Prints the selector-health report on close.

    A LinkedIn markup change makes every verb come back skipped, which reads as
    "nothing to do". Naming the selectors that matched nothing turns that
    silence into something a person can act on.
    """
    from linkedin.automation.session import AutomationUnavailable, LinkedInSession, LoginFailed

    session = None
    try:
        with LinkedInSession.open(
            _app.data_dir,
            headless=headless,
            dry_run=dry_run,
            on_login_needed=None if headless else _pause_for_manual_login,
        ) as session:
            yield session
    except AutomationUnavailable:
        console.print(
            "[red]Browser automation requires extras:[/red] uv sync --extra automation && uv run playwright install chromium"
        )
        raise SystemExit(1)
    except LoginFailed:
        console.print(
            "[red]Not logged in.[/red] Run: linkedin-cli automate login (headful) first, or store credentials with: linkedin-cli automate setup"
        )
        raise SystemExit(1)
    finally:
        if session is not None:
            _report_selector_health(session.selector_health())


def _report_selector_health(report: dict) -> None:
    if report.get("healthy", True):
        return
    console.print(
        "[yellow]Warning: LinkedIn markup may have changed — "
        f"{len(report['misses'])} selector(s) matched nothing.[/yellow]"
    )
    for name, selector in report["selectors"].items():
        console.print(f"  [dim]{name}: {selector}[/dim]")
    console.print("  [dim]Update src/linkedin/automation/selectors.py[/dim]")


def _budget():
    from linkedin.automation.budget import Budget

    return Budget.load(_app.data_dir)


def _load_ai_draft(draft_id: int) -> str:
    """The text of a draft that is known to be the model's, or exit.

    A template, or a row saved before provenance was recorded, is refused:
    nobody knows it is fit to go out under the user's name.
    """
    draft = _app.draft_repo.get(draft_id)
    if not draft:
        console.print(f"[red]Draft #{draft_id} not found.[/red]")
        raise SystemExit(1)
    source = draft.get("source")
    if source != "ai":
        what = "an offline template" if source == "template" else "of unknown provenance"
        console.print(f"[red]Refusing to use draft #{draft_id}: it is {what}, not an AI draft.[/red]")
        console.print("[dim]  Regenerate it with AI available, or pass the text explicitly with --text.[/dim]")
        raise SystemExit(1)
    return draft.get("content", "")


@cli.group("automate")
def automate():
    """Drive LinkedIn in a real browser: search, connect, message, post, engage, apply.

    Uses your own logged-in session with daily budgets and human-like pacing.
    Note: browser automation is against LinkedIn's Terms of Service — use
    deliberately and at your own risk.
    """


@automate.command("setup")
@click.option("--email", prompt=True, help="LinkedIn login email")
@click.option("--password", prompt=True, hide_input=True, help="LinkedIn password")
def automate_setup(email, password):
    """Store LinkedIn credentials in the system keyring."""
    from linkedin.automation.session import setup_credentials

    setup_credentials(email, password)
    console.print("[green]Credentials stored in system keyring.[/green] Next: linkedin-cli automate login")


@automate.command("login")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_login(headless):
    """Log in to LinkedIn and save the session for later commands."""
    with _open_session(headless=headless):
        pass
    console.print(f"[green]Logged in. Session saved to {_app.data_dir.li_session}.[/green]")


@automate.group("limits", invoke_without_command=True)
@click.pass_context
def automate_limits(ctx):
    """Show today's usage against the daily budget (caps live in limits.json)."""
    if ctx.invoked_subcommand is not None:
        return
    table = Table(title="Today's automation budget")
    table.add_column("Kind")
    table.add_column("Used", justify="right")
    table.add_column("Cap", justify="right")
    table.add_column("Remaining", justify="right")
    for kind, row in _budget().summary().items():
        table.add_row(kind, str(row["used"]), str(row["cap"]), str(row["remaining"]))
    console.print(table)
    # soft_wrap: a path must survive copy-paste, and a narrow CI terminal split this one mid-name.
    console.print(f"[dim]Caps: {_app.data_dir.limits}[/dim]", soft_wrap=True)


@automate_limits.command("set")
@click.argument("kind")
@click.argument("cap", type=int)
def automate_limits_set(kind, cap):
    """Set a daily cap, e.g. `automate limits set reaction 10`. Step up only when metrics are clean."""
    from linkedin.automation.budget import KINDS, UnknownKind

    try:
        budget = _budget()
        budget.set_cap(kind, cap)
    except UnknownKind:
        console.print(f"[red]Unknown kind {kind!r}. One of: {', '.join(KINDS)}[/red]")
        raise SystemExit(1)
    console.print(f"[green]{kind}: cap is now {budget.caps[kind]} per day.[/green]")


@automate.command("search")
@click.option("--query", "-q", required=True, help="People search keywords")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_search(query, limit, headless):
    """Preview LinkedIn people search results (no import)."""
    with _open_session(headless=headless) as session:
        result = session.search(query, limit=limit)
    if not result or not result.data:
        console.print(f"[dim]No results ({result.reason or 'empty page'}).[/dim]")
        return
    table = Table(title=f"Search: {query}")
    table.add_column("Name")
    table.add_column("Headline")
    table.add_column("URL")
    for r in result.data:
        table.add_row(r.get("name", ""), r.get("headline", ""), r.get("linkedin_url", ""))
    console.print(table)


@automate.command("import-search")
@click.option("--query", "-q", required=True, help="People search keywords")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_import_search(query, limit, headless):
    """Run a people search and import results into the CRM."""
    with _open_session(headless=headless) as session:
        result = session.search(query, limit=limit)
    if not result:
        console.print(f"[red]Search did not run ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
    added, skipped = import_search_results(result.data, _app.contact_repo)
    console.print(f"[green]Imported {len(added)} contact(s)[/green] ({len(skipped)} already in CRM).")
    for c in added:
        console.print(f"  #{c['id']} {c['name']} — {c.get('title', '')}")


@automate.command("profile")
@click.argument("url")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_profile(url, headless):
    """Scrape a single LinkedIn profile into the CRM."""
    with _open_session(headless=headless) as session:
        result = session.scrape(url)
    contact = import_scraped_profile(result.data, url, _app.contact_repo) if result else None
    if not contact:
        console.print(f"[red]Could not scrape that profile ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
    console.print(f"[green]Imported contact #{contact['id']}:[/green] {contact['name']} — {contact.get('title', '')}")


@automate.command("connect")
@click.argument("contact_id", type=int)
@click.option("--note", default="", help="Connection note text")
@click.option("--draft-id", type=int, default=None, help="Use a saved draft as the note")
@click.option("--dry-run", is_flag=True, help="Navigate but do not send")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_connect(contact_id, note, draft_id, dry_run, headless):
    """Send a connection request to a CRM contact (uses their linkedin_url)."""
    contact = _app.contact_repo.get(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found.[/red]")
        raise SystemExit(1)
    if not contact.get("linkedin_url"):
        console.print(
            f"[red]Contact #{contact_id} has no linkedin_url. Set one with: contacts update {contact_id} --linkedin-url …[/red]"
        )
        raise SystemExit(1)
    if draft_id is not None:
        note = _load_ai_draft(draft_id)
    if len(note) > 300:
        console.print(f"[yellow]Note is {len(note)} chars; LinkedIn caps notes at 300. Truncating.[/yellow]")
        note = note[:300]

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.connect(contact["linkedin_url"], note=note)
    _exit_unless_ok(
        result,
        dry_run_message=f"would send connection request to {contact['name']}.",
        failure_prefix="Could not send the connection request",
    )
    _app.contact_svc.update_contact(contact_id, status="connection_sent")
    console.print(f"[green]Connection request sent to {contact['name']}.[/green] Status → connection_sent")


@automate.command("message")
@click.argument("contact_id", type=int)
@click.option("--text", default="", help="Message text")
@click.option("--draft-id", type=int, default=None, help="Use a saved draft as the message")
@click.option("--dry-run", is_flag=True, help="Navigate but do not send")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_message(contact_id, text, draft_id, dry_run, headless):
    """Send a LinkedIn message to a connected CRM contact."""
    contact = _app.contact_repo.get(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found.[/red]")
        raise SystemExit(1)
    if not contact.get("linkedin_url"):
        console.print(f"[red]Contact #{contact_id} has no linkedin_url.[/red]")
        raise SystemExit(1)
    if draft_id is not None:
        text = _load_ai_draft(draft_id)
    if not text.strip():
        console.print("[red]Nothing to send — pass --text or --draft-id.[/red]")
        raise SystemExit(1)

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.message(contact["linkedin_url"], text)
    _exit_unless_ok(
        result, dry_run_message=f"would message {contact['name']}.", failure_prefix="Could not send the message"
    )
    _app.contact_svc.update_contact(contact_id, status="messaged")
    console.print(f"[green]Message sent to {contact['name']}.[/green] Status → messaged")


@automate.command("post")
@click.option("--text", default="", help="Post content")
@click.option("--draft-id", type=int, default=None, help="Post a saved draft's content")
@click.option("--calendar-id", type=int, default=None, help="Post a scheduled calendar entry (marks it posted)")
@click.option("--dry-run", is_flag=True, help="Do everything except publish")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_post(text, draft_id, calendar_id, dry_run, headless):
    """Publish a post to your LinkedIn feed (from text, a draft, or the content calendar)."""
    calendar_entry = None
    if calendar_id is not None:
        calendar_entry = _app.calendar_repo.get(calendar_id)
        if not calendar_entry:
            console.print(f"[red]Calendar entry #{calendar_id} not found.[/red]")
            raise SystemExit(1)
        if calendar_entry.get("draft_id") is not None:
            draft_id = calendar_entry["draft_id"]
        elif not text:
            console.print(f"[red]Calendar entry #{calendar_id} has no linked draft — pass --text as well.[/red]")
            raise SystemExit(1)
    if draft_id is not None:
        text = _load_ai_draft(draft_id)
    if not text.strip():
        console.print("[red]Nothing to post — pass --text, --draft-id, or --calendar-id.[/red]")
        raise SystemExit(1)

    console.print(Panel(text, title="Post preview"))
    if not dry_run and not click.confirm("Publish this post to LinkedIn?"):
        console.print("[dim]Cancelled.[/dim]")
        return

    _publish(
        text,
        draft_id=draft_id,
        calendar_id=calendar_id if calendar_entry is not None else None,
        dry_run=dry_run,
        headless=headless,
    )


def _publish(text: str, *, draft_id: int | None, calendar_id: int | None, dry_run: bool, headless: bool) -> None:
    """Open a session, post, record the post with its URN, mark the calendar entry."""
    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.post(text)
    _exit_unless_ok(result, dry_run_message="post not published.", failure_prefix="Post failed")
    urn = result.data or ""
    record = _app.post_svc.record_published(text, urn, draft_id=draft_id, calendar_id=calendar_id)
    if urn:
        console.print(f"[green]Post published.[/green] {urn} (post #{record['id']})")
    else:
        console.print(f"[yellow]Post published, but its ID could not be read back ({result.reason}).[/yellow]")
        console.print(
            "[dim]  It is live on LinkedIn and recorded as post "
            f"#{record['id']}, but nothing can join it to its metrics.[/dim]"
        )
    if calendar_id is not None:
        _app.content_svc.mark_posted(calendar_id)
        console.print(f"Calendar entry #{calendar_id} marked posted.")


def _review_feed_comment(post: dict, comment_text: str) -> bool:
    """Show a generated comment and ask before publishing it under the user's name."""
    author = post.get("author") or "Unknown"
    content = str(post.get("content", ""))
    preview = content if len(content) <= 280 else content[:277] + "..."

    console.print(f"\n[bold]Post by {author}[/bold]")
    console.print(f"[dim]{preview}[/dim]")
    console.print(f"[cyan]Proposed comment:[/cyan] {comment_text}")
    return click.confirm("Publish this comment?", default=False)


@automate.command("engage")
@click.option(
    "--contact-id", "contact_ids", type=int, multiple=True, help="Like recent posts of this contact (repeatable)"
)
@click.option(
    "--pinned", is_flag=True, help="Like recent posts of every pinned contact (the people you keep following)"
)
@click.option("--feed", is_flag=True, help="Like posts on your home feed instead")
@click.option("--likes", default=2, help="Likes per target (default 2)")
@click.option("--comments", default=0, help="With --feed: also leave up to N AI-personalized comments")
@click.option("--dry-run", is_flag=True, help="Navigate but do not click Like")
@click.option("--yes", "-y", is_flag=True, help="Publish AI comments without reviewing each one (not recommended)")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_engage(contact_ids, pinned, feed, likes, comments, dry_run, yes, headless):
    """Warm up target contacts by liking their recent posts (or engage your feed).

    With --feed --comments N, browses the feed and leaves short AI-generated
    comments tailored to each post and your profile, on top of liking.

    \b
    Every AI comment is shown for approval before it is published, because the
    text is generated from a stranger's post and goes out under your own name.
    Pass --yes to skip the review (it will not prompt, and it will post).
    """
    if pinned:
        contact_ids = tuple(contact_ids) + tuple(
            c["id"] for c in _app.contact_svc.pinned_contacts() if c["id"] not in contact_ids
        )
        if not contact_ids and not feed:
            console.print("[yellow]No pinned contacts yet. Pin with: linkedin-cli contacts pin ID[/yellow]")
            raise SystemExit(1)
    if not contact_ids and not feed:
        console.print("[red]Pass --contact-id (repeatable), --pinned, and/or --feed.[/red]")
        raise SystemExit(1)
    if comments and not feed:
        console.print("[red]--comments requires --feed (comments run on the feed pipeline).[/red]")
        raise SystemExit(1)
    if comments and yes and not dry_run:
        console.print("[yellow]--yes: AI comments will be published unreviewed under your name.[/yellow]")
    targets = []
    for cid in contact_ids:
        contact = _app.contact_repo.get(cid)
        if not contact:
            console.print(f"[red]Contact #{cid} not found.[/red]")
            raise SystemExit(1)
        if not contact.get("linkedin_url"):
            console.print(f"[yellow]Skipping #{cid} {contact.get('name', '')} — no linkedin_url.[/yellow]")
            continue
        targets.append(contact)

    verb = "would like" if dry_run else "liked"
    total = 0
    with _open_session(headless=headless, dry_run=dry_run) as session:
        for contact in targets:
            result = session.react(likes, profile_url=contact["linkedin_url"])
            liked = int(result.data or 0)
            total += liked
            console.print(
                f"  {contact['name']}: {verb} {liked} post(s)" + ("" if result else f" [dim]({result.reason})[/dim]")
            )
        if feed and comments:
            results = _app.automation_svc.engage_feed(
                session,
                limit=max(likes, comments),
                comment_count=comments,
                approve_comment=publish_unreviewed if yes else _review_feed_comment,
            )
            liked = sum(1 for r in results if r["liked"])
            commented = sum(1 for r in results if r["commented"])
            total += liked
            for r in results:
                marks = ("👍" if r["liked"] else "—") + (" 💬" if r["commented"] else "")
                console.print(f"  {marks} {r['author']}: {r['content_preview']}")
                if r["comment_text"]:
                    console.print(f"      [dim]{r['comment_text']}[/dim]")
                elif r.get("skipped_reason"):
                    console.print(f"      [dim]no comment — {r['skipped_reason']}[/dim]")
            console.print(f"  Feed: {verb} {liked}, {'would comment' if dry_run else 'commented'} {commented}")
        elif feed:
            result = session.react(likes)
            liked = int(result.data or 0)
            total += liked
            console.print(f"  Feed: {verb} {liked} post(s)" + ("" if result else f" [dim]({result.reason})[/dim]"))
    console.print(f"[green]{'Dry run — would react' if dry_run else 'Reacted'} to {total} post(s) total.[/green]")


@automate.command("sync-profile")
@click.option("--headline", default="", help="New headline text")
@click.option(
    "--headline-from-profile",
    is_flag=True,
    help="Use the headline from your profile (the resume repo's copy when it is on this machine)",
)
@click.option("--about-from-profile", is_flag=True, help="Use the About text from your profile (resume repo copy)")
@click.option("--about", default="", help="New About section text")
@click.option("--about-file", type=click.Path(exists=True), default=None, help="Read About text from a file")
@click.option("--dry-run", is_flag=True, help="Show what would change without editing")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_sync_profile(headline, headline_from_profile, about, about_from_profile, about_file, dry_run, headless):
    """Push your headline/About to LinkedIn (pairs with `optimizer` output)."""
    if headline_from_profile:
        profile = _app.profile_repo.get()
        if not profile or not profile.get("headline"):
            console.print("[red]No local profile headline found. Run: linkedin-cli profile setup[/red]")
            raise SystemExit(1)
        headline = profile["headline"]
    if about_from_profile:
        profile = _app.profile_repo.get() and _app.profile_svc.get_profile()
        if not profile or not profile.get("about"):
            console.print(
                "[red]No About text in your profile. Put the resume repo on this machine (LINKEDIN_RESUME_REPO) or pass --about-file.[/red]"
            )
            raise SystemExit(1)
        about = profile["about"]
    if about_file:
        about = Path(about_file).read_text()
    if headline_from_profile or about_from_profile:
        source = (_app.profile_svc.get_profile() or {}).get("copy_source", "local profile file")
        console.print(f"[dim]Copy source: {source}[/dim]")
    if not headline and not about:
        console.print(
            "[red]Nothing to sync — pass --headline/--headline-from-profile and/or --about/--about-from-profile/--about-file.[/red]"
        )
        raise SystemExit(1)

    if headline:
        console.print(Panel(headline, title="New headline"))
    if about:
        console.print(Panel(about, title="New About"))
    if not dry_run and not click.confirm("Apply these changes to your LinkedIn profile?"):
        console.print("[dim]Cancelled.[/dim]")
        return

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.sync_profile(headline=headline, about=about)
    for field_name, status in (result.data or {}).items():
        color = {"updated": "green", "dry_run": "cyan"}.get(status, "red")
        console.print(f"  {field_name}: [{color}]{status}[/{color}]")
    if not result and not result.dry_run:
        console.print(
            "[yellow]LinkedIn's profile editor changes often — update the selectors in selectors.py or edit manually.[/yellow]"
        )
        raise SystemExit(1)


@automate.command("easy-apply")
@click.argument("application_id", type=int)
@click.option("--submit", is_flag=True, help="Actually submit (default stops at the review step)")
@click.option("--resume-repo", default="", help="Path to resume repo checkout (or set LINKEDIN_RESUME_REPO)")
@click.option("--dry-run", is_flag=True, help="Do not open the job page at all")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_easy_apply(application_id, submit, resume_repo, dry_run, headless):
    """Run LinkedIn Easy Apply for a tracked application, using its attached resume PDF."""
    app = _app.application_svc.get_application(application_id)
    if not app:
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    if not app.get("url"):
        console.print(f"[red]Application #{application_id} has no job URL.[/red]")
        raise SystemExit(1)

    resume_path = app.get("resume_path", "")
    if not resume_path:
        # Fall back to matching a variant from the resume repo on the fly
        try:
            ranked = match_variants(app.get("jd_text", ""), repo_root=resume_repo, title=app.get("title", ""))
            if ranked:
                pdf = resolve_pdf(ranked[0]["variant"], "resume", repo_root=resume_repo)
                if pdf:
                    resume_path = str(pdf)
                    console.print(f"Using best-match variant [bold]{ranked[0]['variant']}[/bold]: {pdf}")
        except ResumeRepoError:
            console.print(
                "[yellow]No resume attached and no resume repo configured — applying with your LinkedIn default resume.[/yellow]"
            )
    elif not Path(resume_path).exists():
        console.print(
            f"[yellow]Attached resume {resume_path} no longer exists — applying with your LinkedIn default resume.[/yellow]"
        )
        resume_path = ""

    if dry_run:
        console.print(
            f"[cyan]Dry run:[/cyan] would Easy Apply to {app['url']} with resume: {resume_path or '(LinkedIn default)'}"
        )
        return
    with _open_session(headless=headless) as session:
        result = session.easy_apply(app["url"], resume_path=resume_path, submit=submit)
        if result.reason == "ready_to_submit" and not headless:
            console.print("[yellow]Stopped at the review step. Review the application in the browser window.[/yellow]")
            if click.confirm("Submit it now?"):
                result = session.record_easy_apply_outcome(
                    session.page.easy_apply(resume_path="", submit=True, max_steps=2)
                )
        elif result.reason == "needs_manual_input" and not headless:
            # The automation never invents an answer, so a wizard that asks a
            # question stops here -- which is most of them. With a person at
            # the window that is a hand-off, not a failure: they finish the
            # form and press Submit themselves, and only their word records it.
            console.print(f"[yellow]{(result.data or {}).get('detail', '')}[/yellow]")
            console.print(
                "[yellow]Finish the remaining questions in the browser window and submit it yourself.[/yellow]"
            )
            click.pause("Press any key once you are done (or have closed the form)...")
            if click.confirm("Did you submit the application?"):
                result = session.record_easy_apply_outcome(
                    {"status": "submitted", "detail": "Submitted by hand after automated fill"}
                )
            else:
                result = session.record_easy_apply_outcome(
                    {"status": "ready_to_submit", "detail": "Left unsubmitted; still saved in the CRM"}
                )

    detail = (result.data or {}).get("detail", result.reason)
    if result:
        _app.application_svc.advance(application_id, "applied", notes="Submitted via LinkedIn Easy Apply")
        console.print(f"[green]Submitted![/green] Application #{application_id} → applied")
    elif result.reason == "ready_to_submit":
        console.print(f"[yellow]{detail}[/yellow]")
    elif result.reason == "no_easy_apply":
        console.print(
            f"[yellow]{detail}. This job needs an external application — the resume repo's autoapply pipeline may cover it.[/yellow]"
        )
    else:
        console.print(f"[red]Easy Apply did not complete: {detail}[/red]")
        raise SystemExit(1)


@automate.command("jobs")
@click.option("--query", "-q", required=True, help="Job search keywords")
@click.option("--location", "-L", default="", help="Location filter")
@click.option("--limit", "-l", default=25, help="Max postings to read")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
@click.option("--dry-run", is_flag=True, help="Show results without importing")
def automate_jobs(query, location, limit, headless, dry_run):
    """Search LinkedIn jobs and import the results as scored postings.

    Read-only against LinkedIn. This is what fills the daily plan's
    opportunities section, which reported "No postings above threshold" every
    morning because nothing had ever imported a posting.
    """
    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.jobs(query, location=location, limit=limit)
    results = result.data or []
    if not results:
        console.print(f"[dim]No job results ({result.reason or 'empty page'}).[/dim]")
        return

    table = Table(title=f"Jobs: {query}")
    table.add_column("Title", style="cyan")
    table.add_column("Company")
    table.add_column("Location", style="dim")
    table.add_column("Easy Apply", justify="center")
    for job in results:
        table.add_row(job["title"], job["company"], job["location"], "✓" if job["easy_apply"] else "")
    console.print(table)

    if dry_run:
        console.print(f"[yellow]Dry run — {len(results)} posting(s) not imported.[/yellow]")
        return

    added, skipped = _app.posting_svc.import_job_results(results)
    console.print(
        f"[green]Imported {len(added)} posting(s)[/green]" + (f", skipped {skipped} duplicate(s)" if skipped else "")
    )
