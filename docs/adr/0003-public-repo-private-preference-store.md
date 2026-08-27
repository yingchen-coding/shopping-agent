# Public repository with a gitignored private preference store

The engine — multi-source search, weighted ranking, recall vetoing, price watching — is generic and
worth publishing. The preference store is not: it holds household members' names, birthdates, and the
safety needs attached to specific children. The repository is therefore public while the preference
database is gitignored from the first commit, and no member data ships with the project. Seeding real
household members is done by a script kept outside this repository.

The alternative was a private repository, which removes the leak risk entirely at the cost of the
engine never being useful to anyone else.

## Consequences

This choice is only safe while the gitignore rules actually hold, and the failure mode is permanent —
anything pushed to a public repository stays recoverable from its history even after deletion. Two
sibling projects have already had a `.env` and a runtime log swept in by a broad `git add`, so the
gitignore covers secrets, databases, and runtime artifacts from the outset and pushes are expected to
be checked for member data before they leave the machine. If that discipline ever looks unlikely to
hold, the correct response is to make the repository private, not to relax the rules.
