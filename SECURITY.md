# Security

This library handles repository passwords and API keys. If you find a way it
leaks one, or a way to make it fetch or write something the caller did not ask
for, please report it — quietly first.

## Reporting

Open a [private security advisory][advisory] on the repository. That reaches
the maintainer without the report being public while it is unfixed.

If you cannot use advisories, open a normal issue that says only *"security
report, please get in touch"* and nothing about the finding itself.

Please include, in the advisory:

- what an attacker can do, and what they need to start (a URL? a crafted
  server answer? credentials?);
- the smallest thing that shows it — a few lines of Python, a `curl`, a
  server response;
- the version, from `edusharing.__version__`;
- whether it needs a particular edu-sharing version or configuration.

You will get an acknowledgement within a week. There is no bounty; this is a
small project.

[advisory]: https://github.com/openeduhub/edu-sharing-python-client/security/advisories/new

## What counts

The library's promises, and therefore what a report can be about:

- **Credentials stay where they belong.** They go to the repository host and
  nowhere else. An address with credentials in it is refused; error messages
  and logs mask them; a redirect is reported, never followed.
- **Nothing is fetched on your behalf that you did not name.** Addresses are
  judged before they are used — scheme, embedded credentials, unroutable
  literals, spellings that two parsers read differently.
- **A write that did not happen is not reported as done.** Read-backs prove
  the write against the state before it; a silent drop raises
  `SilentDropError`.
- **A request that may have arrived is not sent again** unless it is safe to
  repeat.

Out of scope: what the edu-sharing instance itself does with your data, and
anything that needs an attacker to already control the machine running the
library.

## Versions

`main` is the one that gets fixes. This is pre-1.0 software: no long-term
support branch, no backporting. Tags exist and are snapshots -- a fix lands on
`main` and in the tag after it, never in one already cut.

| Version | Supported |
|---|---|
| `main` (0.3.6) | ✅ |
| Every tag before that | ❌ |

The number above moves with every release, and a test holds it against
`pyproject.toml`: a table telling you that the version you were told to
install is unsupported is worse than no table.

The development repository
[`janschachtschabel/edu-sharing-python-client`](https://github.com/janschachtschabel/edu-sharing-python-client)
carries the same `main`, and in addition the tags from before this one became
the published home. A report about either belongs in the advisory above.
