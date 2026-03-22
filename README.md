# EM-OptiFlow

A Blender addon that automates repetitive tasks across the 3D production pipeline — handling asset imports, PBR texture processing, naming standardization, SKU management, and batch exports.

**Requires Blender 4.2+**

---

## Features

### Asset Import

- Import objects (FBX, OBJ, glTF/glB) with optional collider meshes
- Import tile/material sets from a texture folder, auto-detecting subfolders and mesh variants (Bullnose, Covebase, flat tiles)
- Auto-resize and compress PBR textures on import (512 – 8192 px)
- Auto-detect and wire PBR maps (Base Color, Roughness, Metallic, Normal, Reflection) into a Principled BSDF shader

### Scene Items

- Manage a list of assets (objects or tiles/materials), each linked to a Blender Collection
- Assign a SKU, subfolder, texture path, and texture size per item
- **Quick Edit** — with Quick Edit enabled, typing while hovering over the Properties panel fills the selected item's SKU directly from the keyboard
    - `Backspace` removes the last character
    - `Del` clears the SKU; `Ctrl+Del` clears all SKUs
    - `Tab` toggles a `?` suffix on the SKU (marks uncertain matches)
- **Isolate** — show only the selected item's collection in the viewport
- Apply naming and material conventions to a single item or all items at once

### Auto Fill SKUs

Fuzzy-match collection names against a product list to fill SKUs automatically.

Three data sources are supported:
| Source | Description |
|--------|-------------|
| **Google Sheets** | OAuth2 login; paste a spreadsheet URL or ID, tabs load automatically |
| **File** | CSV or TSV file from disk |
| **Text Editor** | Paste data directly into Blender's Text Editor |

Matching behaviour:

- Primary score based on name/description tokens
- Dimension tiebreaker (`12x24`, `24x48`, etc.)
- Finish tiebreaker (matte, polished, chiseled, honed, etc.) — penalises candidates with finish terms not present in the collection name
- Rows marked `Discontinued` are skipped automatically
- Uncertain matches (score below confidence threshold) are marked with `?`

### Batch Export

- Configure multiple exporters (glTF, FBX, OBJ), each with its own settings
- Per-exporter: format, output path override, prefix, scale, apply transforms, embed materials, include animations
- Export all items in one click;

---

## Installation

1. Download or clone this repository
2. In Blender, go to **Edit → Preferences → Add-ons → Install**
3. Select the folder (Blender 4.2+ extension install) or zip the folder first
4. Enable **EM-OptiFlow** in the add-on list
5. The panel appears under **Properties → Scene**

---

## Google Sheets Setup

The Google Sheets integration uses OAuth2 with the **Google Sheets API (read-only)**. No Drive API access is required.

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Google Sheets API**
3. Create **OAuth 2.0 credentials** (Desktop app type)
4. Download the credentials file and save it as `credentials.json` in the addon folder
5. In the Auto Fill popup, select **Google Sheets**, then click **Connect to Google**
6. Complete the browser authentication — a `token.json` is saved locally for future sessions
7. Paste a spreadsheet URL or ID; tabs load automatically after a short delay
8. Select a tab and click **Auto Fill**

> `token.json` is generated automatically and should be excluded from version control.

---
