# FiveM AutoFile Toolkit

A small command-line toolkit that automates the boring file work around FiveM servers: resizing item images, cleaning up unused ones, converting old resources to `fxmanifest.lua`, renaming resource folders, and backing up your MySQL database.

> Tool by VomarV

## Features

| # | Tool | What it does |
|---|------|--------------|
| 1 | Resize images | Shrinks every `.png` in a folder to fit 145x124 px (lossless PNG optimization). |
| 2 | Manage images | Moves images that no item uses into a separate folder and logs items that have no image. The item list comes from a JSON file. |
| 3 | Process `__resource.lua` | Converts `__resource.lua` to `fxmanifest.lua` (`fx_version 'cerulean'`, `games { 'gta5' }`, optional `lua54 'yes'`). |
| 4 | Find duplicate images | Reports byte-identical files. Nothing is deleted. |
| 5 | Rename by prefix | Replaces a leading prefix in folder names (and optionally file names). |
| 6 | Database backup | Creates a timestamped `.sql` dump with `mysqldump`. |

## Safety

Options 1, 2, 3 and 5 change files, so each one asks for a **dry run** first (the default). A dry run only prints what would happen. Answer `n` to the dry-run question to apply the changes for real.

- Option 1 overwrites images in place. Keep a backup of the folder.
- Option 2 never overwrites: if a file with the same name already exists in the destination folder, a numbered copy is created.
- Option 3 skips any folder that already has an `fxmanifest.lua`.
- Option 5 skips any rename whose target already exists.
- Option 6 asks for the password with hidden input and passes it through the `MYSQL_PWD` environment variable, so it never shows up in the process list or in error messages.

## Requirements

- Python 3.8+
- `mysqldump` on your PATH (only for option 6)

```bash
pip install -r requirements.txt
```

## Usage

```bash
python AutoFile_Processor.py
```

Pick an option from the menu and answer the prompts. Press `0` to exit. Paths can be pasted or drag-and-dropped; surrounding quotes are removed automatically.

### Items file for option 2

Option 2 reads the list of items and their images from a JSON file:

```json
{
  "weapontint_mk2_5": { "name": "weapontint_mk2_5", "image": "weapontint_black.png" },
  "bandage": { "name": "bandage", "image": "bandage.png" }
}
```

- Image names are matched case-insensitively.
- Images in the folder that no item uses are moved to the "unused images" folder.
- Items whose image is missing are printed and written to the "missing images" log file.

### What option 3 produces

For a resource containing:

```lua
resource_manifest_version '44febabe-d386-4d18-afbe-5e627f4af937'
client_script 'client.lua'
```

the result is a new `fxmanifest.lua`:

```lua
fx_version 'cerulean'
games { 'gta5' }

client_script 'client.lua'
```

The old `__resource.lua` is removed once the new file is written. `lua54 'yes'` is added only if you confirm it, because it can break older resources.

## Notes

- Option 4 only finds files with identical bytes, not images that merely look alike.
- Option 5 does not update references inside your scripts. If other resources refer to a renamed folder, update them separately.
- Add `SLEEP = 0.05` (near the top of the script) if you want slower, easier-to-read output.
