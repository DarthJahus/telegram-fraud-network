from inspect import currentframe
from time import sleep
from datetime import datetime
from telegram_checker.config.constants import (
    EMOJI,
    STATS_INIT
)
from telegram_checker.config.api import SLEEP_BETWEEN_CHECKS
from telegram_mdml.telegram_mdml import TelegramEntity
from telegram_mdml.telegram_mdml import (
    TelegramMDMLError,
    MissingFieldError,
    InvalidFieldError,
    InvalidTypeError
)
from telegram_checker.utils.helpers import get_date_time, print_debug
from telegram_checker.mdml_utils.mdml_file import write_id_to_md
from telegram_checker.mdml_utils.mdml_file import process_and_update_file
from telegram_checker.mdml_utils.mdml_parser import get_last_status, extract_telegram_identifiers
from telegram_checker.utils.output_display import (
    print_stats,
    print_no_status_block,
    print_dry_run_summary,
    print_recovered_ids,
    print_discovered_usernames,
    print_status_changed_files
)
from telegram_checker.telegram_utils.status_checker import check_entity_with_fallback
from telegram_checker.utils.logger import get_logger

LOG = get_logger()


def should_skip_entity(entity, skip_time_seconds, skip_statuses, skip_unknown=True):
    """
    Determines if an entity should be skipped based on its last status.

    Args:
        entity (TelegramEntity): Telegram MDML entity
        skip_time_seconds (int or None): Skip if checked within this many seconds
        skip_statuses (list or None): Skip if last status is in this list
        skip_unknown (default: True): Skip when last_stats is Unknown

    Returns:
        tuple: (should_skip, reason) where reason explains why it was skipped
    """
    last_status, last_datetime, has_status_block = get_last_status(entity)

    if last_status is None:
        # No previous status, don't skip
        return False, None

    # Check if we should skip based on status
    if skip_statuses and last_status in skip_statuses:
        return True, f"last status is '{last_status}' (exception)"

    # Check if we should skip based on time
    # IMPORTANT: Never skip 'unknown' status based on time (always re-check)
    if skip_time_seconds is not None and not skip_unknown or last_status != 'unknown':
        time_since_check = datetime.now() - last_datetime
        if time_since_check.total_seconds() < skip_time_seconds:
            hours = int(time_since_check.total_seconds() / 3600)
            mins = int((time_since_check.total_seconds() % 3600) / 60)
            return True, f"checked {hours}h {mins}m ago (status: {last_status})"

    return False, None


def full_check(client, args, ignore_statuses, md_files, skip_time_seconds):
    # Statistics
    stats = STATS_INIT.copy()
    # Store results for dry-run summary
    results = []
    status_changed_files = []
    no_status_block_results = []
    recovered_ids = []  # List of {file, id, method, written}
    discovered_usernames = []  # List of {file, old_username, new_username, status}
    try:
        for md_file in md_files:
            # parsing the file through MDML
            try:
                entity = TelegramEntity.from_file(md_file)
                LOG.info()
                LOG.info(f"\\[[{md_file.name}\\]]", EMOJI["file"])

                # Check type filter
                try:
                    entity_type = entity.get_type()
                except (InvalidTypeError, MissingFieldError):
                    entity_type = None
                except Exception as e:
                    LOG.error(f"{EMOJI['error']} Error: {e}")
                    entity_type = None

                if args.type and 'all' not in args.type and entity_type not in args.type:
                    stats['skipped'] += 1
                    stats['skipped_type'] += 1
                    LOG.info(f"Skipping entity with type {entity_type} not {', neither '.join(args.type)}", emoji=EMOJI['skip'])
                    continue

                # Extract ALL identifiers upfront
                try:
                    expected_id = entity.get_id()
                except InvalidFieldError:
                    expected_id = None
                except Exception as e:
                    LOG.error(f"{EMOJI['error']} Error: {e}")
                    expected_id = None

                identifiers, is_invite = extract_telegram_identifiers(entity)

                # If no ID AND no identifiers, skip entirely
                if not expected_id and not identifiers:
                    LOG.info(f"  {EMOJI["skip"]} Skipped: No identifier found")
                    stats['skipped'] += 1
                    stats['skipped_no_identifier'] += 1
                    continue

                # Get last status info
                last_status, last_datetime, has_status_block = get_last_status(entity)

                # Check if we should skip based on last status
                should_skip, skip_reason = should_skip_entity(entity, skip_time_seconds, args.skip, not args.no_skip_unknown)
                if should_skip:
                    LOG.info(f"  {EMOJI["skip"]} Skipped: ({skip_reason})")
                    stats['skipped'] += 1
                    if 'checked' in skip_reason and 'ago' in skip_reason:
                        stats['skipped_time'] += 1
                    elif 'last status' in skip_reason:
                        stats['skipped_status'] += 1
                    continue

                # Check entity status with priority fallback
                status, restriction_details, actual_id, actual_username, method_used, display_id = check_entity_with_fallback(
                    client, expected_id, identifiers, is_invite, stats
                )

                # Check and write the retrieved ID
                if actual_id and not expected_id:
                    id_written = False

                    # Write ID retrieved via invite, if --write-id
                    if method_used == 'invite' and args.write_id and not args.dry_run:
                        if write_id_to_md(md_file, actual_id):
                            LOG.info(f"  {EMOJI['saved']} ID written to file: `{actual_id}`")
                            id_written = True
                        else:
                            LOG.info(f"  {EMOJI['info']} ID already present in file.")

                    # Add to list of retrieved ID
                    recovered_ids.append({
                        'file': md_file.name,
                        'id': actual_id,
                        'method': method_used,
                        'written': id_written
                    })

                # Track discovered / changed usernames
                if actual_username:
                    username = entity.get_username(allow_strikethrough=False)
                    if username:
                        existing_username = username.value  # username without @
                    else:
                        existing_username = None

                    # Cas 1 : Discovered username not in MDML
                    if not existing_username:
                        LOG.info(f"  {EMOJI['handle']} Username discovered: @{actual_username}")
                        discovered_usernames.append({
                            'file': md_file.name,
                            'old_username': None,
                            'new_username': actual_username,
                            'status': 'discovered'
                        })

                    # Cas 2 : Username has changed AND is different from username in MDML
                    elif existing_username.lower() != actual_username.lower():
                        LOG.info(f"  {EMOJI['change']} Username changed: @{existing_username} → @{actual_username}")
                        discovered_usernames.append({
                            'file': md_file.name,
                            'old_username': existing_username,
                            'new_username': actual_username,
                            'status': 'changed'
                        })

                # Update statistics
                stats['total'] += 1
                if status in stats:
                    stats[status] += 1
                else:
                    stats['error'] += 1

                # Process result and update file if needed
                should_ignore = ignore_statuses and status in ignore_statuses
                if should_ignore:
                    stats['ignored'] += 1

                should_track_change, _ = process_and_update_file(
                    md_file, status, restriction_details, actual_id,
                    expected_id, last_status,
                    should_ignore, args.dry_run
                )

                # Store result for reports
                result = {
                    'file': md_file.name,
                    'identifier': display_id,
                    'status': status,
                    'timestamp': get_date_time(),
                    'emoji': EMOJI.get(status, EMOJI["no_emoji"]),
                    'restriction_details': restriction_details
                }
                results.append(result)

                # Track files without status block
                if not has_status_block:
                    no_status_block_results.append(result)

                # Track status changes
                if should_track_change:
                    status_changed_files.append({
                        'file': md_file.name,
                        'old': last_status,
                        'new': status
                    })

                # Sleep between checks to avoid rate limiting
                if md_file != md_files[-1]:
                    sleep(SLEEP_BETWEEN_CHECKS)
            except FileNotFoundError:
                LOG.error("File not found.", EMOJI['error'])
            except TelegramMDMLError:
                LOG.error("Parsing failed.", EMOJI['error'])
            except Exception as e:
                LOG.error("Failed to read MDML entity from file.", EMOJI['error'])
                print_debug(e,currentframe().f_code.co_name)
    except KeyboardInterrupt:
        client.disconnect()
        if args.no_exit: input('Press any key to exit')
        exit(0)
    finally:
        # Always disconnect, even if there's an error
        client.disconnect()
    # Final statistics
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
