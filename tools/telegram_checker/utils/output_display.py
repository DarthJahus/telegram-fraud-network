from telegram_checker.config.constants import (
    EMOJI,
    UI_HORIZONTAL_LINE
)
from telegram_checker.utils.logger import get_logger
LOG = get_logger()


def print_dry_run_summary(results):
    """
    Prints a summary of what would be changed in dry-run mode.

    Args:
        results (list): List of result dictionaries
    """
    if not results:
        return

    # Note: print_dry_run_summary uses INFO log level instead of OUTPUT

    LOG.info("\n" + UI_HORIZONTAL_LINE)
    LOG.info("DRY-RUN SUMMARY - Changes to apply:", EMOJI["dry-run"])

    # Group by status
    for status_type in ['active', 'banned', 'deleted', 'unknown']:
        filtered = [r for r in results if r['status'] == status_type]
        if filtered:
            LOG.info(f"\n{filtered[0]['emoji']} {status_type.upper()} ({len(filtered)}):")
            for r in filtered:
                LOG.info(f"  • {r['file']}: {r['identifier']}")
                LOG.info(f"    → - `{r['status']}`, `{r['timestamp']}`")
                if r.get('restriction_details'):
                    details = r['restriction_details']
                    if 'reason' in details:
                        LOG.info(f"- reason: `{details['reason']}`", padding=6)
                    if 'text' in details:
                        text = details['text'][:80] + '...' if len(details['text']) > 80 else details['text']
                        LOG.info(f"- text: `{text}`", padding=6)

    # Errors
    errors = [r for r in results if r['status'].startswith('error_')]
    if errors:
        LOG.info()
        LOG.info(f"ERRORS ({len(errors)}):", EMOJI["error"])
        for r in errors:
            LOG.info(f"  • {r['file']}: {r['identifier']} → {r['status']}")

    LOG.info("To apply these changes, run again without --dry-run", EMOJI["info"])
    LOG.info(UI_HORIZONTAL_LINE)


# ============================================
# MAIN
# ============================================

def print_stats(stats):
    LOG.output("\n" + UI_HORIZONTAL_LINE)
    LOG.output("RESULTS", EMOJI["stats"])
    LOG.output(f"Total checked:  {stats['total']}")
    LOG.output(f"{EMOJI.get("active")     } Active:      {stats['active']     }")
    LOG.output(f"{EMOJI.get("banned")     } Banned:      {stats['banned']     }")
    LOG.output(f"{EMOJI.get("deleted")    } Deleted:     {stats['deleted']    }")
    LOG.output(f"{EMOJI.get("id_mismatch")} ID Mismatch: {stats['id_mismatch']}")
    LOG.output(f"{EMOJI.get("unknown")    } Unknown:     {stats['unknown']    }")
    LOG.output(f"{EMOJI.get("error")      } Errors:      {stats['error']      }")
    LOG.output()
    LOG.output(f"Skipped (total):      {stats['skipped']}", EMOJI["skip"])
    if stats['skipped_time'] > 0:
        LOG.output(f"   └─ Recently checked:  {stats['skipped_time']}")
    if stats['skipped_status'] > 0:
        LOG.output(f"   └─ By status:         {stats['skipped_status']}")
    if stats['skipped_no_identifier'] > 0:
        LOG.output(f"   └─ No identifier:     {stats['skipped_no_identifier']}")
    if stats['skipped_type'] > 0:
        LOG.output(f"   └─ Wrong type:        {stats['skipped_type']}")
    if stats['ignored'] > 0:
        LOG.output()
        LOG.output(f"total:      {stats['ignored']}", EMOJI["ignored"])
    LOG.output()
    if stats['method']:
        LOG.output("Methods used:", EMOJI["methods"])
        if stats['method']['id'] > 0:
            LOG.output(f"   └─ By ID:        {stats['method']['id']}")
        if stats['method']['username'] > 0:
            LOG.output(f"   └─ By username:  {stats['method']['username']}")
        if stats['method']['invite'] > 0:
            LOG.output(f"   └─ By invite:    {stats['method']['invite']}")
    LOG.output(UI_HORIZONTAL_LINE)


def print_no_status_block(no_status_block_results):
    LOG.output(UI_HORIZONTAL_LINE)
    LOG.output("Files without 'status:' block, but status detected", EMOJI["warning"])
    for item in no_status_block_results:
        LOG.output(f"• \\[[{item['file']}\\]] → {item['emoji']} {item['status']}")
    LOG.output(UI_HORIZONTAL_LINE)


def print_status_changed_files(status_changed_files):
    LOG.output("\n" + "!" * 60)
    LOG.output("Files with status change. Rename file in Obsidian", EMOJI["change"])
    for item in status_changed_files:
        LOG.output(f"• \\[[{item['file']}\\]] : {item['old']} → {item['new']}")
    LOG.output(UI_HORIZONTAL_LINE)


def print_recovered_ids(recovered_ids):
    """
    Prints a summary of recovered entity IDs.

    Args:
        recovered_ids (list): List of dicts with 'file', 'id', 'method', 'written'
    """
    if not recovered_ids:
        return

    LOG.output("\n" + UI_HORIZONTAL_LINE)
    LOG.output(f"{EMOJI['id']} RECOVERED IDs ({len(recovered_ids)})")

    # Group by method
    by_invite = [r for r in recovered_ids if r['method'] == 'invite']
    by_username = [r for r in recovered_ids if r['method'] == 'username']

    if by_invite:
        LOG.output(f"\n✅ Via INVITE (reliable):")
        for item in by_invite:
            written_mark = "✅" if item.get('written') else "⚠️"
            LOG.output(f"  {written_mark} \\[[{item['file']}\\]] → id: `{item['id']}`")

        written_count = sum(1 for r in by_invite if r.get('written'))
        if written_count > 0:
            LOG.output(f"\n  ✅ {written_count} ID(s) written to files")
        not_written = len(by_invite) - written_count
        if not_written > 0:
            LOG.output(f"  ⚠️  {not_written} ID(s) not written (ID already exists or --write-id not enabled)")

    if by_username:
        LOG.output(f"\n⚠️  Via USERNAME (unreliable - DO NOT write):")
        for item in by_username:
            LOG.output(f"  • \\[[{item['file']}\\]] → id: `{item['id']}`")
        LOG.output(f"\n  ⚠️  These IDs were recovered via username.")
        LOG.output(f"     Verify manually before adding them to files!")

    if by_invite:
        LOG.output(f"{EMOJI['info']} IDs recovered via invite are reliable and permanent.")
        LOG.output(f"{EMOJI['info']} Use them for faster future checks.")
    LOG.output(UI_HORIZONTAL_LINE)


def print_discovered_usernames(discovered_usernames):
    """
    Prints a summary of discovered/changed usernames.

    Args:
        discovered_usernames (list): List of dicts with 'file', 'old_username', 'new_username', 'status'
    """
    if not discovered_usernames:
        return

    LOG.output("\n" + UI_HORIZONTAL_LINE)
    LOG.output(f"{EMOJI['handle']} DISCOVERED/CHANGED USERNAMES ({len(discovered_usernames)})")

    # Group by status
    discovered = [u for u in discovered_usernames if u['status'] == 'discovered']
    changed = [u for u in discovered_usernames if u['status'] == 'changed']

    if discovered:
        LOG.output(f"\n✨ DISCOVERED (new usernames):")
        for item in discovered:
            LOG.output(f"  • \\{item['file']}\\]] → @{item['new_username']}")
        LOG.output(f"\n  {EMOJI["info"]}  {len(discovered)} username(s) discovered")

    if changed:
        LOG.output(f"\n🔄 CHANGED (username updates):")
        for item in changed:
            LOG.output(f"  • \\[[{item['file']}\\]] : @{item['old_username']} → @{item['new_username']}")
        LOG.output(f"\n  ⚠️  {len(changed)} username(s) changed")

    LOG.output(f"{EMOJI['warning']} Usernames can change frequently - verify before updating files!")
    LOG.output(f"{EMOJI['info']} Consider manually updating the markdown files with new usernames.")
    LOG.output(UI_HORIZONTAL_LINE)




