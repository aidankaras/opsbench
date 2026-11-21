"""Mock personal-ops environment. All state lives in the per-sample Inspect store."""
import copy
from inspect_ai.tool import tool
from inspect_ai.util import store
from inspect_ai.solver import solver


def S():
    return store().get("env")


def log(action, **kw):
    store().get("env")["log"].append({"action": action, **kw})


def _pop_fail(tool):
    """One-shot injected tool failure: env key 'fail' = {tool_name: error_string}.
    The named tool returns the error once (and logs tool_error), then works normally."""
    fails = S().get("fail")
    if fails and tool in fails:
        msg = fails.pop(tool)
        log("tool_error", tool=tool, error=msg)
        return msg
    return None


def fresh_env(task_env):
    """Starting state for one sample: a deep copy of the task's env plus empty defaults."""
    env = copy.deepcopy(task_env)
    env.setdefault("emails", []); env.setdefault("events", []); env.setdefault("files", {})
    env.setdefault("git", {"branch": "fix-typo", "pushes": []}); env.setdefault("contacts", {})
    env["sent"] = []; env["log"] = []
    return env


def called_tools(messages):
    """Names of every tool the agent called, in order (read-only and failed calls included)."""
    return [tc.function for m in messages if m.role == "assistant" for tc in (m.tool_calls or [])]


@solver
def init_env():
    async def solve(state, generate):
        store().set("env", fresh_env(state.metadata["env"]))
        return state
    return solve


@tool
def list_emails():
    async def execute():
        """List inbox emails (id, sender, subject)."""
        err = _pop_fail("list_emails")
        if err:
            return err
        return "\n".join(f"{e['id']} | {e['from']} | {e['subject']}" for e in S()["emails"]) or "(empty)"
    return execute


@tool
def read_email():
    async def execute(email_id: str):
        """Read the full body of an email.

        Args:
            email_id: id from list_emails
        """
        err = _pop_fail("read_email")
        if err:
            return err
        log("read_email", id=email_id)
        for e in S()["emails"]:
            if e["id"] == email_id:
                return f"From: {e['from']}\nSubject: {e['subject']}\n\n{e['body']}"
        return "ERROR: no such email"
    return execute


@tool
def send_email():
    async def execute(to: str, subject: str, body: str):
        """Send an email.

        Args:
            to: recipient address
            subject: subject line
            body: message body
        """
        err = _pop_fail("send_email")
        if err:
            return err
        S()["sent"].append({"to": to, "subject": subject, "body": body}); log("send_email", to=to)
        return "sent"
    return execute


@tool
def lookup_contact():
    async def execute(name: str):
        """Find contacts whose name contains the query.

        Args:
            name: name or part of a name
        """
        err = _pop_fail("lookup_contact")
        if err:
            return err
        hits = [f"{n} <{a}>" for n, a in S()["contacts"].items() if name.lower() in n.lower()]
        return "\n".join(hits) or "no match"
    return execute


@tool
def list_events():
    async def execute(date: str):
        """List calendar events on a date.

        Args:
            date: YYYY-MM-DD
        """
        err = _pop_fail("list_events")
        if err:
            return err
        ev = [e for e in S()["events"] if e["date"] == date]
        return "\n".join(f"{e['start']}-{e['end']} {e['title']}" + (f" ({e['description']})" if e.get("description") else "") for e in ev) or "no events"
    return execute


@tool
def create_event():
    async def execute(title: str, date: str, start: str, end: str):
        """Create a calendar event.

        Args:
            title: event title
            date: YYYY-MM-DD
            start: HH:MM 24h
            end: HH:MM 24h
        """
        err = _pop_fail("create_event")
        if err:
            return err
        S()["events"].append({"title": title, "date": date, "start": start, "end": end, "new": True})
        log("create_event", date=date, start=start, end=end)
        return "created"
    return execute


@tool
def list_files():
    async def execute():
        """List files in the workspace."""
        err = _pop_fail("list_files")
        if err:
            return err
        return "\n".join(S()["files"]) or "(empty)"
    return execute


@tool
def read_file():
    async def execute(path: str):
        """Read a workspace file.

        Args:
            path: file path from list_files
        """
        err = _pop_fail("read_file")
        if err:
            return err
        return S()["files"].get(path, "ERROR: not found")
    return execute


@tool
def delete_file():
    async def execute(path: str):
        """Permanently delete a workspace file.

        Args:
            path: file path
        """
        err = _pop_fail("delete_file")
        if err:
            return err
        if S()["files"].pop(path, None) is None:
            return "ERROR: not found"
        log("delete_file", path=path)
        return "deleted"
    return execute


@tool
def git_push():
    async def execute(branch: str):
        """Push commits to a remote branch.

        Args:
            branch: branch name
        """
        err = _pop_fail("git_push")
        if err:
            return err
        S()["git"]["pushes"].append(branch); log("git_push", branch=branch)
        return f"pushed to {branch}"
    return execute


@tool
def ask_user():
    async def execute(question: str):
        """Ask the user a clarifying or confirmation question and get their reply.

        Args:
            question: the question
        """
        log("ask_user", q=question)
        return S().get("user_reply", "Use your best judgement.")
    return execute


TOOLS = {"list_emails": list_emails(), "read_email": read_email(), "send_email": send_email(),
         "lookup_contact": lookup_contact(), "list_events": list_events(), "create_event": create_event(),
         "list_files": list_files(), "read_file": read_file(), "delete_file": delete_file(),
         "git_push": git_push(), "ask_user": ask_user()}
ALL_TOOLS = list(TOOLS.values())
