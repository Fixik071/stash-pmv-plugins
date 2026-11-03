// What this Stash version can do – found out once by asking its schema (not by a version number), so a feature that
// needs a newer Stash only shows up where it works. v32 = Stash 0.32 or newer (Scene has a production date).

import { gql } from "./api.js";

let asked = null;
let known = null; // the answer, once it is in (for code that can't wait)
export const capsNow = () => known;
const names = (x, k) => new Set(((x && x[k]) || []).map((f) => f.name));

export function caps() {
  if (!asked) {
    asked = gql(`query Caps {
      s: __type(name: "Scene") { fields { name } }
      su: __type(name: "SceneUpdateInput") { inputFields { name } }
      su2: __type(name: "StudioUpdateInput") { inputFields { name } }
      g: __type(name: "Group") { fields { name } }
    }`)
      .then((d) => {
        const scene = names(d.s, "fields");
        return {
          v32: scene.has("production_date"),
          productionDate: scene.has("production_date") && names(d.su, "inputFields").has("production_date"),
          childStudios: names(d.su2, "inputFields").has("child_ids"),
          subGroups: names(d.g, "fields").has("sub_groups"),
        };
      })
      .then((c) => (known = c))
      .catch(() => ({ v32: false, productionDate: false, childStudios: false, subGroups: false }));
  }
  return asked;
}
