## ![OptiFlow](images/optiflow-featured.png)

A Blender addon that automates repetitive tasks across the 3D production pipeline — handling asset imports, PBR texture processing, mesh presets, naming standardization, ID management, and batch exports. Designed to produce highly optimized assets by compressing and resizing textures with minimal perceptual quality loss, keeping file sizes as small as possible without compromising visual fidelity. By enforcing consistent naming conventions and automating error-prone manual steps, it also reduces human error and makes production reviews faster and more reliable.

**Requires Blender 5.0+** / **3D Viewport sidebar → OptiFlow tab**.

## Features

### Groups & Items

Assets are organized in a two-level hierarchy: **Groups** contain **Items**, each item holding one or more scene objects.

- Create groups and items manually, or have them generated automatically on import
- Rename a group or item — all linked objects are renamed automatically with their prefix preserved (`MESH_`, `COL_`, `PLACER_`, `SNAP_`, `GUIDE_`)
- Renaming a group to the name of an existing group opens a merge dialog
- **Drag to reorder** — click and drag any row to move it; items can cross group boundaries; double-click to select the item's objects in the viewport
- **Duplicate** a group or item with deep-copied scene objects (`Ctrl+D` or menu)
- **Delete** removes the item and its exclusive scene objects; `Ctrl+Click` deletes the entry but keeps objects in the scene

### Item Types

| Type       | Description                                                                                                                                    |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Object** | Imports one or more 3D files (FBX, OBJ, glTF, ABC, USD, DAE, STL, PLY, X3D) as the mesh, plus an optional collider file (auto-prefixed `COL_`) |
| **Preset** | Spawns a template mesh from the built-in preset library instead of importing a file                                                            |

When adding an Object item, any animation actions found in the file are pushed to NLA tracks automatically.

### Mesh Presets

Presets are FBX template meshes stored in the `meshes/` folder inside the addon directory.

- Any `MESH_*.fbx` file is discovered automatically and appears as a preset option
- **Set as Preset** applies a template mesh to the currently selected scene objects, preserving their existing materials
- Import and manage custom presets under **Edit → Preferences → Add-ons → OptiFlow → Presets**

### Texture Import

Textures are selected in the **Add Item** dialog and processed in the background — Blender stays responsive while PIL handles the heavy work.

Supported PBR map types (auto-detected by filename suffix):

`Color` · `ORM` · `Normal` · `Roughness` · `Metallic` · `Occlusion` · `Reflection` · `Specular` · `Emission` · `Opacity` · `Glossiness` · `SSS` · `Transmission` · `Sheen` · `Coat`

Processing steps performed automatically:

- **ORM combination** — Roughness, Metallic, and Occlusion maps are merged into a single ORM texture (R = Occlusion, G = Roughness, B = Metallic)
- **Opacity merge** — when an Opacity map is present, it is merged into the Color map's alpha channel
- **Reflection inversion** — Reflection maps are inverted to the Roughness convention
- **Multiple texture folders** — scanning a folder with subfolders creates one texture group per subfolder; navigate groups with the First / Prev / Next / Last arrows in the dialog

Per-import overrides (optional toggles per field):

| Override        | Effect                                                                                   |
| --------------- | ---------------------------------------------------------------------------------------- |
| **Roughness**   | Replaces or multiplies the roughness value; baked as a solid fill if no map is available |
| **Metallic**    | Same as Roughness, for the metallic channel                                              |
| **Size**        | Resizes all textures to the selected resolution (32 – 8192 px)                           |
| **Compression** | Auto · Smallest · Balanced · Higher Quality                                              |
| **Format**      | Auto · JPG · PNG · WEBP                                                                  |

A progress bar is shown in the main panel while textures are being processed.

### Material Building

After textures are loaded, a **Principled BSDF** material is built and assigned automatically:

- Correct colorspace per map type (Non-Color for data maps, sRGB for color)
- ORM texture split with a Separate Color node (G → Roughness, B → Metallic)
- Alpha/transparency wired and blend mode set when an RGBA image is detected
- Normal map node inserted automatically
- Nodes arranged in a clean columnar layout

When multiple mesh objects share an item and multiple Color maps are present, each object receives its own color texture.

### Auto Fill

Fuzzy-match item and group names against an external product list to fill item names (e.g. SKUs) automatically.

Three data sources:

| Source            | Description                                                          |
| ----------------- | -------------------------------------------------------------------- |
| **Google Sheets** | OAuth2 login; paste a spreadsheet URL or ID, tabs load automatically |
| **File**          | CSV or TSV file from disk                                            |
| **Text Editor**   | Paste data directly into Blender's Text Editor                       |

Matching uses weighted multi-signal scoring:

| Signal         | Weight | Source                                                       |
| -------------- | ------ | ------------------------------------------------------------ |
| `group_finish` | 25%    | Finish / type tokens extracted from the group name           |
| `group_size`   | 25%    | Dimension tokens (`12x24`, `24x48`, …) from the group name   |
| `group_shape`  | 20%    | Shape tokens matched against the sheet's shape/format column |
| `item_color`   | 20%    | The item name, treated as the color                          |
| `alias`        | 10%    | The item's alias field                                       |

Additional matching behavior:

- Rows with a `Status` column value other than `Active` (including `Discontinued`) are skipped
- Items scoring below the confidence threshold are marked `INVALID`
- A prefix and suffix can be appended to every matched value
- Header row offset is configurable for sheets with metadata rows above the headers
- Settings are remembered between sessions

### Viewport Isolation

| Mode                      | Behavior                                                                                                    |
| ------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Isolate (object mode)** | Hides all objects except the current selection; red border overlay                                          |
| **Isolate (edit mode)**   | Hides unselected geometry; auto-reveals when exiting edit mode                                              |
| **Item Isolate**          | Shows only the selected item's objects; yellow border overlay; automatically follows list selection changes |

Isolation state is preserved across undo/redo and file reload.

### Batch Export

Configure multiple exporters, each with independent settings:

| Setting          | Formats        | Description                                                   |
| ---------------- | -------------- | ------------------------------------------------------------- |
| Format           | glTF, FBX, OBJ | Output file format                                            |
| Override Path    | All            | Per-exporter output folder (overrides the shared export path) |
| Prefix           | All            | Prepended to each filename                                    |
| Scale            | FBX, OBJ       | Global export scale                                           |
| Apply Transforms | FBX, OBJ       | Bake object transforms                                        |
| Embed Materials  | glTF, FBX, OBJ | Embed or reference textures                                   |
| Animations       | All            | Include animation data                                        |
| Tangents         | glTF           | Export tangent vectors                                        |
| Image Type       | glTF           | Auto / JPEG / WebP                                            |
| Quality          | glTF           | JPEG/WebP compression (50 – 100%)                             |
| Frame Range      | OBJ            | Start and end frame for animation export                      |

Each group exports into a subfolder named after the group. Materials are temporarily renamed to `Mat`, `Mat_1`, `Mat_2`, … during export for consistent naming, then restored immediately after.

A confirmation dialog shows the full file list, flags any files that would be overwritten, and warns if any mesh contains N-gons.

### Keyboard Shortcuts

These shortcuts are active while the cursor is over the OptiFlow panel:

| Shortcut    | Action                       |
| ----------- | ---------------------------- |
| `Up / Down` | Navigate the list            |
| `Ctrl+G`    | Add a new group              |
| `Ctrl+E`    | Edit the selected item       |
| `Ctrl+D`    | Duplicate the selected entry |
| `Ctrl+Del`  | Delete the selected entry    |

### Update Checker

A background check against the GitHub releases API runs on startup. The indicator in the panel header turns orange when an update is available.

---

## Installation

1. Download the latest `.zip` from the [Releases](https://github.com/gchibeni/OptiFlow/releases) page
2. In Blender, go to **Edit → Preferences → Add-ons → Install from Disk**
3. Select the downloaded `.zip` file
4. Enable **OptiFlow** in the add-on list
5. The panel appears in the **3D Viewport sidebar → OptiFlow tab** (or press `N`)

---

## Google Sheets Setup

The Google Sheets integration uses OAuth2 with the **Google Sheets API (read-only scope only)**.

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Google Sheets API**
3. Create **OAuth 2.0 credentials** (Desktop app type)
4. Download the credentials file and save it as `credentials.json` in the addon folder
5. In the Auto Fill dialog, select **Google Sheets**, then click **Connect to Google**
6. Complete browser authentication — a `token.json` is saved locally for future sessions
7. Paste a spreadsheet URL or ID; tabs load automatically
8. Select a tab and click **Fill**

> `token.json` is generated automatically and should be excluded from version control.

---

## Custom Mesh Presets

1. Prepare an FBX file containing a single mesh object
2. Name it `MESH_<TYPENAME>.fbx` (e.g. `MESH_BULLNOSE.fbx`)
3. Go to **Edit → Preferences → Add-ons → OptiFlow → Presets** and click **Import Preset**, or drop the file directly into the `meshes/` folder inside the addon directory
4. The new preset appears immediately in the Mesh dropdown

Presets can be renamed or deleted from the same Preferences panel.
