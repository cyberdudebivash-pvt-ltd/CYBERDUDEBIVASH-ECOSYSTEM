# Release Governance

## Production invariant

`main` is the production control branch. It must never accept a change unless the change arrives through a pull request and the mandatory GitHub Actions checks succeed on the latest eligible commit.

The source-of-truth contract is `config/release-governance.json`. The exact GitHub repository ruleset payload is `config/github-main-ruleset.json`.

## Mandatory server-side controls

The active ruleset named **CYBERDUDEBIVASH Production Main Guard** must:

- target only `refs/heads/main`;
- require pull requests;
- require all review conversations to be resolved;
- require `validate`, `Analyze (python)`, and `Analyze (actions)`;
- require the branch to be up to date before those checks satisfy the gate;
- pin mandatory checks to the GitHub Actions integration;
- block branch deletion;
- block non-fast-forward/force pushes;
- expose no bypass actors.

`CodeRabbit` remains an advisory review signal rather than a hard merge dependency, so a third-party outage cannot deadlock production recovery.

## Activation

The GitHub REST create/update ruleset endpoint requires **Administration: write** for this repository. Never store that credential in the repository, Actions variables, issue text, or chat logs.

On a trusted operator workstation, check out this branch and provide a short-lived fine-grained token scoped only to this repository with **Administration: write**.

PowerShell:

```powershell
$env:GH_ADMIN_TOKEN = '<short-lived-token>'
python scripts/release_governance.py apply
python scripts/release_governance.py verify-live
Remove-Item Env:GH_ADMIN_TOKEN
```

Linux/macOS:

```bash
export GH_ADMIN_TOKEN='<short-lived-token>'
python scripts/release_governance.py apply
python scripts/release_governance.py verify-live
unset GH_ADMIN_TOKEN
```

The installer is idempotent: it creates the named ruleset when absent and updates the same ruleset when it already exists.

## Release sequence

1. Open a pull request into `main`.
2. Do not merge while any mandatory check is pending, skipped unexpectedly, cancelled, or failed.
3. Resolve all review threads.
4. Rebase/update the branch when GitHub reports it is behind `main`; mandatory checks must rerun on the eligible latest state.
5. Merge only after GitHub's server-side ruleset reports the PR mergeable.
6. Confirm the push-triggered Repository Quality and CodeQL jobs are green on the resulting production SHA.

## Break-glass

There is no standing bypass actor. Emergency recovery is performed by temporarily changing the ruleset through an authenticated administrator action, documenting the incident, applying the minimum recovery change, then immediately restoring and re-verifying this contract. A permanent administrator bypass defeats the purpose of the production gate and is prohibited.

## Drift monitoring

`.github/workflows/release-governance.yml` runs daily and on demand. It fails if the required named ruleset is absent or not active. `Repository Quality` separately validates the checked-in contract on every pull request and production push.
