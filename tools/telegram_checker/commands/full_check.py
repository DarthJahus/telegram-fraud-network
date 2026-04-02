from inspect import currentframe
from time import sleep
from telegram_checker.config.constants import EMOJI, make_stats
from telegram_checker.config.api import SLEEP_BETWEEN_CHECKS
from telegram_checker.telegram_utils.entity_fetcher import iter_md_entities
from telegram_checker.utils.helpers import get_date_time, print_debug
from telegram_checker.mdml_utils.mdml_file import write_id_to_md
from telegram_checker.mdml_utils.mdml_file import process_and_update_file
from telegram_checker.utils.output_display import (
    print_stats,
    print_no_status_block,
    print_dry_run_summary,
    print_recovered_ids,
    print_discovered_usernames,
    print_status_changed_files
)
from telegram_checker.telegram_utils.status_checker import check_entity_with_fallback
from telegram_checker.utils.logger import get_logger, create_progress_bar

LOG = get_logger()


def full_check(client, args, ignore_statuses, md_files, skip_time_seconds):
    # Statistics
    stats = make_stats('check')
    # Store results for dry-run summary
    results = []
    status_changed_files = []
    no_status_block_results = []
    recovered_ids = []  # List of {file, id, method, written}
    discovered_usernames = []  # List of {file, old_username, new_username, status}

    progress_bar = create_progress_bar(LOG, md_files, "Checking")
    progress_bar['bar'].start()

    try:
        for item in iter_md_entities(args, md_files, stats, skip_time_seconds, progress_bar=progress_bar):
            md_file          = item['md_file']
            entity           = item['entity']
            expected_id      = item['expected_id']
            identifiers      = item['identifiers']
            is_invite        = item['is_invite']
            last_status      = item['last_status']
            has_status_block = item['has_status_block']

            try:
                status, restriction_details, actual_id, actual_username, method_used, display_id = \
                    check_entity_with_fallback(client, expected_id, identifiers, is_invite, stats)

                if actual_id and not expected_id:
                    id_written = False
                    if method_used == 'invite' and args.write_id and not args.dry_run:
                        if write_id_to_md(md_file, actual_id):
                            LOG.info(f"  {EMOJI['saved']} ID written to file: `{actual_id}`")
                            id_written = True
                        else:
                            LOG.info(f"  {EMOJI['info']} ID already present in file.")
                    recovered_ids.append({
                        'file': md_file.name, 'id': actual_id,
                        'method': method_used, 'written': id_written
                    })

                if actual_username:
                    username = entity.get_username(allow_strikethrough=False)
                    existing_username = username.value if username else None
                    if not existing_username:
                        LOG.info(f"  {EMOJI['handle']} Username discovered: @{actual_username}")
                        discovered_usernames.append({
                            'file': md_file.name, 'old_username': None,
                            'new_username': actual_username, 'status': 'discovered'
                        })
                    elif existing_username.lower() != actual_username.lower():
                        LOG.info(f"  {EMOJI['change']} Username changed: @{existing_username} → @{actual_username}")
                        discovered_usernames.append({
                            'file': md_file.name, 'old_username': existing_username,
                            'new_username': actual_username, 'status': 'changed'
                        })

                stats['total'] += 1
                stats[status] = stats.get(status, 0) + 1

                should_ignore = ignore_statuses and status in ignore_statuses
                if should_ignore:
                    stats['ignored'] += 1

                should_track_change, _ = process_and_update_file(
                    md_file, status, restriction_details, actual_id,
                    expected_id, last_status, should_ignore, args.dry_run
                )

                result = {
                    'file': md_file.name, 'identifier': display_id,
                    'status': status, 'timestamp': get_date_time(),
                    'emoji': EMOJI.get(status, EMOJI["no_emoji"]),
                    'restriction_details': restriction_details
                }
                results.append(result)

                if not has_status_block:
                    no_status_block_results.append(result)
                if should_track_change:
                    status_changed_files.append({'file': md_file.name, 'old': last_status, 'new': status})

                if md_file != md_files[-1]:
                    sleep(SLEEP_BETWEEN_CHECKS)

            except Exception as e:
                LOG.error("Error processing entity.", EMOJI['error'])
                print_debug(e, currentframe().f_code.co_name)

            except KeyboardInterrupt:
                stats['skipped'] += 1
                stats['skipped_user'] += 1
                LOG.info('CTRL+C detected. Entity skipped by user. Press CTRL+C again to quit.', emoji=EMOJI['skip'])
                try:
                    sleep(2)
                except KeyboardInterrupt:
                    raise
                continue

    finally:
        progress_bar['bar'].stop()
        LOG.set_progress(None)
        # Final statistics
        LOG.throttle = False
        print_stats(stats)
        # Dry-run summary
        if args.dry_run:
            print_dry_run_summary(results)
        if status_changed_files:
            print_status_changed_files(status_changed_files)
        if no_status_block_results:
            print_no_status_block(no_status_block_results)
        if recovered_ids:
            print_recovered_ids(recovered_ids)
        if discovered_usernames:
            print_discovered_usernames(discovered_usernames)
