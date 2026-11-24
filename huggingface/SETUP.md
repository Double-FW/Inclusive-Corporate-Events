# GitHub to Hugging Face dataset sync

Source: https://github.com/Double-FW/Inclusive-Corporate-Events  
Destination: https://huggingface.co/datasets/GarethFW/Inclusive_Corporate_Events

## One-time owner setup

The workflow requires a Hugging Face token with read and write access to this dataset. Never put the token in a file, issue, commit, or chat.

1. Create a fine-grained token for only `GarethFW/Inclusive_Corporate_Events`, with read and write access to that dataset.
2. In the GitHub source repository, open **Settings → Secrets and variables → Actions → New repository secret**.
3. Set **Name** to `HF_TOKEN`.
4. Paste the token into **Secret** and save.
5. Confirm this sync setup is on the default `main` branch.
6. Open **Actions → Sync Inclusive Corporate Events dataset → Run workflow**, choose `main`, then select **Run workflow**.
7. Confirm the run succeeds and inspect the Hugging Face dataset's **Files and versions** page for the source revision.

The destination is fixed in the reviewed configuration. The publisher only updates files it owns and preserves unrelated dataset files and visibility. The destination must already exist as an initialized dataset repository.

## Ongoing behaviour

- A push to `main` that changes an approved source document, exporter, configuration, setup guide, licence, or workflow triggers a sync.
- A scheduled sync runs each Monday at 07:23 UTC. GitHub may delay scheduled runs.
- A manual workflow run is available.
- Pull requests do not publish; publishing is restricted to the default branch.
- If managed files have not changed, no Hugging Face commit is created.
- Managed files are the dataset card, MIT licence copy, full-document and heading-level JSONL records, provenance, record schema, and export manifest.
- The full-document and section configurations overlap by design. The document records contain the README, AGENTS instructions, and three event guidance documents. Section records come from the lifecycle, detailed guide, and venue and delivery checklist.
- The GitHub source must remain public and declare MIT. The workflow uses GitHub's read-only token for that check; `HF_TOKEN` is available only to the publishing step.

If a run fails, open that run's job log. Common causes include a missing or incorrectly scoped token, a destination that has not been initialized, source visibility or licence changes, or an API error. Do not share credentials in issues, logs, or chat.
