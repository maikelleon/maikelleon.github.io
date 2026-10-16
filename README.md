# maikelleon.github.io

Personal academic website of Maikel Leon, PhD.

## Putting the site online (one time, about 15 minutes)

1. **Create a GitHub account** at github.com. If the username `maikelleon` is free, take it, because the site address will be `https://<username>.github.io`.
2. **Create a repository.** Click **New repository**, name it exactly `maikelleon.github.io` (use your username if it differs), choose **Public**, and click **Create repository**.
3. **Upload the files.** On the new repository page, click **uploading an existing file**, then drag in everything inside this folder and click **Commit changes**.
   On a Mac, press **Cmd + Shift + .** in Finder first so the hidden `.github` folder is visible and gets uploaded too. It holds the update buttons.
4. **Turn on the website.** Go to **Settings → Pages**. Under *Build and deployment*, set *Source* to **Deploy from a branch**, the branch to **main**, the folder to **/ (root)**, and click **Save**. The site appears at `https://maikelleon.github.io` within a few minutes.
5. **Allow the update buttons to save changes.** Go to **Settings → Actions → General**, scroll to *Workflow permissions*, choose **Read and write permissions**, and click **Save**.
6. **Bookmark the controls page:** `https://maikelleon.github.io/admin.html`. It is not linked from the site and search engines are told to ignore it.
7. **Visitor stats (optional, free):** sign up at goatcounter.com and choose a code such as `maikelleon`. Then open **Edit journals and impact factors** on the controls page, find `"goatcounter": ""`, type your code between the quotes, and commit. The Visitor stats button starts working and counting begins. GoatCounter sets no cookies, so the site needs no cookie banner.

## The controls page (admin.html)

**Add or change content.** Each of these opens a short form. Fill it in and press **Create**. Within about a minute the site changes, and the form gets a reply saying exactly what changed. Only forms you submit yourself are applied; anyone else's are ignored.

| Button | Result |
|---|---|
| Add a media appearance | New card in Media, sorted by year. Several links become a multi-segment card |
| Add an award or certification | New line in Honors |
| Add a talk or session | New line under Talks |
| Show or clear announcement | Banner at the top of the site, or removes it |
| Show or hide sections | Turns Consulting or Talks on or off |
| Remove an item | Removes one media card, award, or talk matching the words you give |

Spanish fields are optional. When left blank, the English text shows on the Spanish version too.

**Replace files.** Drag a photo (headshot) or a Word/PDF file (CV) into the upload page and press **Commit changes**. Photos are cropped square; Word files become PDF.

**Maintenance.**

| Button | Result |
|---|---|
| Update publications and citations | Pulls papers from ORCID and OpenAlex, citations from Google Scholar, and newly reviewed journals from ORCID. Also runs on the 1st of each month |
| Check for broken links | Tests every outside link. Runs on the 2nd of each month; if a link is dead you get an email (a GitHub issue) listing it |
| Visitor stats | Opens your GoatCounter dashboard (step 7 above) |
| Download a backup | The whole site as a zip |

Each run shows a short report: open the **Actions** tab and click the latest run.

## How the publication update decides what to show

- **Featured list:** a paper in your ORCID record is featured only if it appears in a journal listed in `data/config.json` under `journals`. That list holds the 14 journals from the CV, with their impact factors. Papers are listed newest first. To feature a new journal, add one line there, for example `"journal name in lowercase": {"name": "Journal Name", "if": 3.2}`.
- **All works:** every item in ORCID appears in a collapsible list under the featured papers.
- **Venue names:** when a database spells a journal or conference oddly (all capitals, or "Proceedings of the ..."), the clean name goes under `venue_names` in `data/config.json` and every update uses it.
- **Retracted papers:** papers that OpenAlex flags as retracted, and retraction notices, are left out of every list.
- **Corrections:** when a database has a wrong year, page range, or title, add it under `overrides` in `data/config.json`, keyed by DOI. The featured papers' titles are kept there in sentence case; a new paper shows the publisher's capitalization until you add its title there.
- **Links on each paper:** the DOI; **PDF** when OpenAlex finds an open-access copy (**Open access** when the free copy is a repository page); and **BibTeX**, which copies a complete citation, or downloads it as a .bib file when the browser blocks copying. To link a free copy of your own, add `"pdf": "https://..."` under the paper's DOI in `overrides`.
- **Your name** always prints as "Leon, M.", never "León".
- **Undergraduate research:** papers you co-author with the students named under `students` in `data/config.json` are listed in the Teaching section, newest first. To add a student, add their name as it appears on the paper. Award badges and code links go under `student_extras`, keyed by DOI.
- **Links beside a paper:** extra links, such as the FCM Expert website and video demo beside the 2018 FCM Expert paper, go under `paper_links` in `data/config.json`, keyed by DOI.
- **Folding:** the three newest journal articles and one row of media cards stay open; the rest of the year's articles, earlier articles, older appearances, talks, certifications, the course lists, the student papers, and the full ORCID list sit in sections that expand when clicked, each showing how many items it holds. Section backgrounds alternate black and white on their own, even when you hide a section.
- **Journals reviewed for:** the list under Service is `reviewed_for` in `data/content.json`, grouped by publisher and alphabetical within each group. Each entry has a `journal` and a `publisher`. Each update also adds any new journal from the peer-review section of your ORCID record, with its publisher (reviews you record in Web of Science reach ORCID on their own). To hide a journal for good, add its name under `reviews_exclude` in `data/config.json`.
- **Skills:** the chips under About come from `skills` in `data/content.json`: groups with an English and Spanish name, each holding skills in both languages. They were drawn from your papers and the courses you teach. Edit them there.
- **Research numbers:** citations and h-index in the Research section come from Google Scholar (or the saved values).
- **Google Scholar** has no official data feed and sometimes blocks automated requests. When that happens the saved numbers stay as they are and the run report says so. You can also edit them by hand under `metrics` in `data/config.json`.

## Moving to your own domain later

If you buy a domain such as maikelleon.com, connect it under **Settings → Pages → Custom domain**, then replace `maikelleon.github.io` in the link-preview lines near the top of `index.html` (they control how the site looks when shared on LinkedIn or WhatsApp), or ask Claude to do it.

## Undoing a change

Every update is saved as a separate entry in the repository history (**commits**). To undo one, open it and choose **Revert**, or ask Claude to do it.

## Files

- `index.html`: the site. Sections between `<!-- NAME:START -->` and `<!-- NAME:END -->` markers are rewritten by the update. Everything else is edited by hand.
- `admin.html`: the controls page.
- `data/content.json`: media, honors, talks, skills, journals reviewed for, announcement, and which sections show. The forms edit this file.
- `.github/ISSUE_TEMPLATE/`: the forms.
- `assets/`: headshot and CV.
- `data/config.json`: ORCID iD, Scholar ID, journal list, corrections, saved metrics, GoatCounter code.
- `scripts/`: the update and upload scripts.
- `.github/workflows/`: the automation behind the buttons.
- `uploads/`: drop zone for a new headshot or CV.
