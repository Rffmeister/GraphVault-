# GraphVault

**The fastest auto-MOC generator for Obsidian – pure Python, zero plugins**

→ Scans **25,000+ folders in ~12 seconds**  
→ Creates perfect hierarchical MOCs automatically  
→ No Obsidian plugin required – just drop & run

![GraphVault in action](https://raw.githubusercontent.com/Rffmeister/GraphVault-/main/demo.gif)  
*(GIF coming in the next hours – meanwhile, try it and see the progress bar fly!)*

## What it does (and no one else does this well)

- Lightning-fast folder scanning (single `iterdir()` pass – no more 5-minute waits)
- One MOC per folder with:
  - Parent link (up)
  - All subfolder links (down)
  - Files grouped by type: Text • Code • Images • Videos • Audio • Data • Archives
- Smart file handling:
  - ≤2 MB → copied directly into the folder
  - >2 MB → lightweight proxy note in `!_adjuntos` (keeps your vault fast & clean)
- Batch processing with progress bar + checkpoint system (pause & resume anytime)
- Full deletion sync (removes stale MOCs/files automatically)
- Windows lock + detailed log

Output: a ready-to-use `graph-vault-archivos` folder you can drop straight into Obsidian.

## 30-second Quickstart

```bash
# 1. Download the script
curl -L https://github.com/Rffmeister/GraphVault-/releases/latest/download/GraphVault.py -o GraphVault.py

# 2. Create a folder called "input" next to the script and put your vault/chaos inside
# 3. Run
python GraphVault.py
