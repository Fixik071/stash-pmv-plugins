// "To StashDB": sends what Stash knows of a scene or a performer to a stash-box as a draft (Stash's own
// submitStashBoxSceneDraft / submitStashBoxPerformerDraft – the same as "Submit to stash-box" in classic Stash).
// A draft is not published: it opens on the box's site, where you check it, fill in what's missing and submit it as an
// edit for the box's users to vote on. A box that doesn't take drafts answers with an error, which is shown.

import { toast, menu, confirmDialog } from "../ui.js";
import { t } from "../i18n.js";
import { gql } from "../api.js";

const site = (endpoint) => String(endpoint).replace(/\/graphql\/?$/i, "");
const boxName = (b) => b.name || site(b.endpoint).replace(/^https?:\/\//, "");

function pickBox(boxes, anchor) {
  if (boxes.length === 1 || !anchor) return Promise.resolve(boxes[0]);
  return new Promise((resolve) => {
    menu(anchor, boxes.map((b) => ({ label: boxName(b), detail: site(b.endpoint), run: () => resolve(b) })));
  });
}

export async function sendDraft(kind, id, anchor) {
  let boxes;
  try {
    const d = await gql(`query DraftBoxes { configuration { general { stashBoxes { endpoint name } } } }`);
    boxes = (d.configuration.general.stashBoxes || []).filter((b) => b.endpoint);
  } catch (e) {
    return toast(e.message, "error");
  }
  if (!boxes.length) return toast(t("No StashDB (stash-box) set up. Add it in classic Stash → Settings → Metadata Providers."), "error");
  const box = await pickBox(boxes, anchor);
  if (!box) return;

  const what = kind === "scene" ? t("this scene") : t("this performer");
  const ask = await confirmDialog({
    title: t("Send a draft to {box}?", { box: boxName(box) }),
    text: t("Stash sends {what} – title, date, links, picture and what else is filled in – to {box} as a draft. Nothing is published yet: you check the draft on the site and submit it there yourself.", { what, box: boxName(box) }),
    ok: t("Send draft"),
  });
  if (!ask.ok) return;

  const m = kind === "scene" ? "submitStashBoxSceneDraft" : "submitStashBoxPerformerDraft";
  let draft;
  try {
    const r = await gql(`mutation($i: StashBoxDraftSubmissionInput!) { ${m}(input: $i) }`, { i: { id: String(id), stash_box_endpoint: box.endpoint } });
    draft = r[m];
  } catch (e) {
    // StashDB gives new accounts read access only – drafts need the EDIT role, which its moderators give
    if (/not authori[sz]ed/i.test(e.message))
      return toast(t("Your {box} account may only read – it can't send drafts. Ask for edit access on {box}.", { box: boxName(box) }), "error");
    return toast(t("{box} didn't take the draft: {err}", { box: boxName(box), err: e.message }), "error");
  }
  if (!draft) return toast(t("{box} didn't take the draft: {err}", { box: boxName(box), err: t("no answer") }), "error");

  const url = site(box.endpoint) + "/drafts/" + encodeURIComponent(draft);
  // opened from a click of its own – a window opened after the request would be stopped as a pop-up
  toast(t("Draft sent to {box}", { box: boxName(box) }), "", { label: t("Open draft"), run: () => window.open(url, "_blank", "noopener") });
}
