"""AutoFile Processor - Tool by VomarV (revised).

Options:
  1 - Resize PNG images
  2 - Manage images (move unused, log missing) using a JSON item list
  3 - Convert __resource.lua -> fxmanifest.lua
  4 - Find duplicate images
  5 - Rename folders (and optionally files) by prefix
  6 - Create MySQL database backup
"""

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from getpass import getpass

import pyfiglet
from colorama import Fore, Style, init
from PIL import Image

init(autoreset=True)

MAX_IMAGE_SIZE = (145, 124)
SLEEP = 0  # set to e.g. 0.05 if you want a slower, easier-to-read output


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def pause():
    time.sleep(SLEEP)


def print_credits():
    print(Fore.CYAN + pyfiglet.figlet_format("Tool by VomarV"))


def ask(prompt):
    """Ask for text input; strips whitespace and drag-and-drop quotes."""
    return input(Fore.YELLOW + prompt + Style.RESET_ALL).strip().strip('"').strip("'")


def ask_dir(prompt, create=False):
    """Ask for a directory path and validate it. Returns None on failure."""
    path = ask(prompt)
    if not path:
        print(Fore.RED + "Path cannot be empty.")
        return None
    if not os.path.isdir(path):
        if create:
            os.makedirs(path, exist_ok=True)
            print(Fore.GREEN + f"Created folder: {path}")
        else:
            print(Fore.RED + f"Folder not found: {path}")
            return None
    return path


def confirm(prompt, default=False):
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = ask(prompt + suffix).lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def unique_path(path):
    """Return a path that does not exist yet (adds _1, _2, ... if needed)."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


# ----------------------------------------------------------------------
# 1. Resize images
# ----------------------------------------------------------------------
def resize_images(image_folder, dry_run=False):
    """Shrink every PNG to fit MAX_IMAGE_SIZE (lossless PNG optimization)."""
    count = 0
    for image_name in sorted(os.listdir(image_folder)):
        if not image_name.lower().endswith(".png"):
            continue
        image_path = os.path.join(image_folder, image_name)
        try:
            if dry_run:
                print(Fore.LIGHTBLUE_EX + f"[dry-run] Would resize: {image_name}")
            else:
                with Image.open(image_path) as img:
                    img = img.convert("RGBA")
                    img.thumbnail(MAX_IMAGE_SIZE)
                    img.save(image_path, format="PNG", optimize=True)
                print(Fore.LIGHTBLUE_EX + f"Resized: {image_name}")
            count += 1
            pause()
        except Exception as e:
            print(Fore.RED + f"Error resizing {image_name}: {e}")
    print(Fore.GREEN + f"Done. {count} image(s) processed.")


# ----------------------------------------------------------------------
# 2. Manage images
# ----------------------------------------------------------------------
def load_items(items_file):
    """Load items from JSON: {"key": {"name": "...", "image": "..."}, ...}"""
    with open(items_file, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, dict) or not items:
        raise ValueError("Items file must be a non-empty JSON object.")
    for key, item in items.items():
        if not isinstance(item, dict) or "image" not in item:
            raise ValueError(f"Item '{key}' must contain an 'image' field.")
        item.setdefault("name", key)
    return items


def manage_images(image_folder, not_found_folder, not_found_image_file, items, dry_run=False):
    """Move images not used by any item; log items that have no image."""
    if not dry_run:
        os.makedirs(not_found_folder, exist_ok=True)
        log_dir = os.path.dirname(os.path.abspath(not_found_image_file))
        os.makedirs(log_dir, exist_ok=True)
        if os.path.exists(not_found_image_file):
            os.remove(not_found_image_file)

    used_images = {item["image"].lower() for item in items.values()}
    existing = {}

    for image_name in sorted(os.listdir(image_folder)):
        image_path = os.path.join(image_folder, image_name)
        if not os.path.isfile(image_path):
            continue
        existing[image_name.lower()] = image_name
        if image_name.lower() not in used_images:
            if dry_run:
                print(Fore.YELLOW + f"[dry-run] Unused image would be moved: {image_name}")
            else:
                target = unique_path(os.path.join(not_found_folder, image_name))
                shutil.move(image_path, target)
                print(Fore.YELLOW + f"Unused image: {image_name} - moved to {not_found_folder}")
            pause()

    missing = 0
    for item in items.values():
        if item["image"].lower() not in existing:
            missing += 1
            print(Fore.RED + f"Item: {item['name']} does not have an image.")
            if not dry_run:
                with open(not_found_image_file, "a", encoding="utf-8") as f:
                    f.write(f"{item['name']} does not have an image.\n")
            pause()
    print(Fore.GREEN + f"Image management completed. Missing images: {missing}")


# ----------------------------------------------------------------------
# 3. Lua resource files
# ----------------------------------------------------------------------
RE_MANIFEST_VERSION = re.compile(r"^\s*resource_manifest_version\b")
RE_FX_VERSION = re.compile(r"^\s*fx_version\b")
RE_GAMES = re.compile(r"^\s*games?\b")
RE_LUA54 = re.compile(r"^\s*lua54\b")


def process_lua_files(lua_directory, add_lua54=False, dry_run=False):
    """Convert __resource.lua to fxmanifest.lua (cerulean)."""
    pattern = os.path.join(lua_directory, "**", "__resource.lua")
    files = glob.glob(pattern, recursive=True)
    if not files:
        print(Fore.YELLOW + "No __resource.lua files found.")
        return

    converted = skipped = 0
    for file_path in files:
        new_path = os.path.join(os.path.dirname(file_path), "fxmanifest.lua")
        if os.path.exists(new_path):
            print(Fore.YELLOW + f"Skipped (fxmanifest.lua already exists): {file_path}")
            skipped += 1
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()

            has_fx = any(RE_FX_VERSION.match(l) for l in lines)
            has_games = any(RE_GAMES.match(l) for l in lines)
            has_lua54 = any(RE_LUA54.match(l) for l in lines)
            body = [l for l in lines if not RE_MANIFEST_VERSION.match(l)]

            header = []
            if not has_fx:
                header.append("fx_version 'cerulean'")
            if not has_games:
                header.append("games { 'gta5' }")
            if add_lua54 and not has_lua54:
                header.append("lua54 'yes'")
            content = "\n".join(header + [""] + body).rstrip() + "\n"

            if dry_run:
                print(Fore.CYAN + f"[dry-run] Would convert: {file_path} -> {new_path}")
            else:
                tmp_path = new_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                os.replace(tmp_path, new_path)  # new file is complete before the old one goes
                os.remove(file_path)
                print(Fore.CYAN + f"Processed and renamed: {file_path} -> {new_path}")
            converted += 1
        except Exception as e:
            print(Fore.RED + f"Error processing {file_path}: {e}")
    print(Fore.GREEN + f"Lua files done. Converted: {converted}, skipped: {skipped}")


# ----------------------------------------------------------------------
# 4. Duplicate images
# ----------------------------------------------------------------------
def file_md5(path, chunk_size=1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicate_images(image_folder):
    """Report byte-identical files (does not delete anything)."""
    hash_dict = {}
    duplicates = 0
    for image_name in sorted(os.listdir(image_folder)):
        image_path = os.path.join(image_folder, image_name)
        if not os.path.isfile(image_path):
            continue
        try:
            digest = file_md5(image_path)
        except Exception as e:
            print(Fore.RED + f"Error processing {image_name}: {e}")
            continue
        if digest in hash_dict:
            duplicates += 1
            print(Fore.RED + f"Duplicate found: {image_name} and {hash_dict[digest]}")
        else:
            hash_dict[digest] = image_name
    print(Fore.GREEN + f"Duplicate search completed. Duplicates found: {duplicates}")


# ----------------------------------------------------------------------
# 5. Rename by prefix
# ----------------------------------------------------------------------
def change_folder_rights(directory, old_rights, new_rights, include_files=False, dry_run=False):
    """Replace a leading prefix in folder names (and optionally file names)."""
    if not old_rights:
        print(Fore.RED + "Old prefix cannot be empty.")
        return

    ok = failed = 0

    def rename(root, name):
        nonlocal ok, failed
        if not name.startswith(old_rights):
            return
        old_path = os.path.join(root, name)
        new_path = os.path.join(root, new_rights + name[len(old_rights):])
        if os.path.exists(new_path):
            print(Fore.RED + f"Skipped (target exists): {new_path}")
            failed += 1
            return
        try:
            if dry_run:
                print(Fore.GREEN + "[dry-run] " + Fore.YELLOW + old_path + Fore.CYAN + " -> " + Fore.YELLOW + new_path)
            else:
                os.rename(old_path, new_path)
                print(Fore.GREEN + "Renamed: " + Fore.YELLOW + old_path + Fore.CYAN + " -> " + Fore.YELLOW + new_path)
            ok += 1
            pause()
        except Exception as e:
            failed += 1
            print(Fore.RED + f"Error renaming {old_path}: {e}")

    if include_files:
        for root, _, files in os.walk(directory):
            for file_name in files:
                rename(root, file_name)

    for root, dirs, _ in os.walk(directory, topdown=False):  # inner folders first
        for dir_name in dirs:
            rename(root, dir_name)

    color = Fore.GREEN if failed == 0 else Fore.YELLOW
    print(color + f"Rename finished. Renamed: {ok}, failed/skipped: {failed}")


# ----------------------------------------------------------------------
# 6. Database backup
# ----------------------------------------------------------------------
def create_database_backup():
    print(Fore.LIGHTCYAN_EX + "Creating a backup of the database...")
    db_host = ask("Enter the database host (default: localhost): ") or "localhost"
    db_user = ask("Enter the database username: ")
    db_password = getpass("Enter the database password (hidden): ")
    db_name = ask("Enter the database name: ")
    if not db_user or not db_name:
        print(Fore.RED + "Username and database name are required.")
        return
    backup_directory = ask_dir("Enter the directory to save the backup: ", create=True)
    if not backup_directory:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = os.path.join(backup_directory, f"{db_name}_backup_{timestamp}.sql")

    command = [
        "mysqldump",
        f"--host={db_host}",
        f"--user={db_user}",
        "--single-transaction",
        "--routines",
        "--default-character-set=utf8mb4",
        db_name,
    ]
    env = os.environ.copy()
    env["MYSQL_PWD"] = db_password  # keeps the password out of the process list

    try:
        with open(backup_file, "wb") as output_file:
            result = subprocess.run(command, stdout=output_file, stderr=subprocess.PIPE, env=env)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "mysqldump failed")
        print(Fore.GREEN + f"Backup created successfully: {backup_file}")
    except FileNotFoundError:
        print(Fore.RED + "mysqldump was not found. Install MySQL client tools or add them to PATH.")
        _remove_quietly(backup_file)
    except Exception as e:
        # The password is never part of the command line or of this message.
        print(Fore.RED + f"Backup failed: {e}")
        _remove_quietly(backup_file)


def _remove_quietly(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ----------------------------------------------------------------------
# Menu
# ----------------------------------------------------------------------
MENU = [
    "1 - Resize images",
    "2 - Manage images (unused images and missing images)",
    "3 - Process __resource.lua files",
    "4 - Find duplicate images",
    "5 - Rename folders (change prefix)",
    "6 - Create Database Backup",
    "0 - Exit",
]


def run_choice(choice):
    if choice == "1":
        folder = ask_dir("Enter the path to the images folder: ")
        if folder:
            dry = confirm("Dry run (show only, change nothing)?", default=True)
            if dry or confirm("Images are overwritten in place. Continue?"):
                resize_images(folder, dry)

    elif choice == "2":
        folder = ask_dir("Enter the path to the images folder: ")
        if not folder:
            return
        items_file = ask("Enter the path to the items JSON file: ")
        try:
            items = load_items(items_file)
        except Exception as e:
            print(Fore.RED + f"Could not load items: {e}")
            print(Fore.YELLOW + 'Expected format: {"key": {"name": "item", "image": "item.png"}}')
            return
        not_found_folder = ask("Enter the path to the folder for unused images: ")
        not_found_image_file = ask("Enter the path to the file for missing images: ")
        if not not_found_folder or not not_found_image_file:
            print(Fore.RED + "Both paths are required.")
            return
        dry = confirm("Dry run (show only, change nothing)?", default=True)
        manage_images(folder, not_found_folder, not_found_image_file, items, dry)

    elif choice == "3":
        folder = ask_dir("Enter the path to the directory containing __resource.lua files: ")
        if folder:
            add_lua54 = confirm("Add lua54 'yes'? (can break older resources)")
            dry = confirm("Dry run (show only, change nothing)?", default=True)
            process_lua_files(folder, add_lua54, dry)

    elif choice == "4":
        folder = ask_dir("Enter the path to the images folder: ")
        if folder:
            find_duplicate_images(folder)

    elif choice == "5":
        folder = ask_dir("Directory path: ")
        if not folder:
            return
        old_rights = ask("Old prefix: ")
        new_rights = ask("New prefix: ")
        if not old_rights:
            print(Fore.RED + "Old prefix cannot be empty.")
            return
        include_files = confirm("Rename files too (not only folders)?")
        dry = confirm("Dry run (show only, change nothing)?", default=True)
        change_folder_rights(folder, old_rights, new_rights, include_files, dry)

    elif choice == "6":
        create_database_backup()


def main():
    print_credits()
    while True:
        print(Fore.LIGHTCYAN_EX + "\nPlease choose an option:")
        for line in MENU:
            print(Fore.LIGHTMAGENTA_EX + line)
        choice = ask("Enter your choice: ")
        if choice == "0":
            break
        if choice not in {"1", "2", "3", "4", "5", "6"}:
            print(Fore.RED + "Invalid choice.")
            continue
        try:
            run_choice(choice)
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\nCancelled.")
        except Exception as e:
            print(Fore.RED + f"Unexpected error: {e}")

    input(Fore.CYAN + "Press Enter to close...")


if __name__ == "__main__":
    main()
