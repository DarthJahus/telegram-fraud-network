from telegram_checker.utils.helpers import get_date_time
from telegram_checker.utils.logger import get_logger
LOG = get_logger()


def format_entity_mdml(info):
    """
    Formats entity information as MDML using the MDML library.

    Args:
        info: dict returned by fetch_entity_info()

    Returns:
        str: MDML formatted text
    """
    from mdml.models import Document, Field, FieldValue
    from telethon.tl.types import Channel, Chat, User

    if not info:
        return ""

    now = get_date_time()
    now_date, now_time = now.split(' ')

    # Create Document with frontmatter
    doc = Document(raw_content='')
    if info.get('type'):
        doc.frontmatter['type'] = info['type']

    # ID
    if info['id']:  # ToDo: Still check why ID is duplicated by the main check routine
        doc.fields['id'] = Field(
            name='id',
            is_list=False,
            values=[FieldValue(value= str(info['id']) if info['id'] else "ID")],
            raw_content=''
        )

    # Status
    doc.fields['status'] = Field(
        name='status',
        is_list=True,
        values=[FieldValue(value='active', date=now_date, time=now_time)],
        raw_content=''
    )

    doc.fields['discovered'] = None

    # Username
    if info.get('username'):
        doc.fields['username'] = Field(
            name='username',
            is_list=False,
            values=[FieldValue(
                value=f"@{info['username']}",
                details=f"[link](https://t.me/{info['username']})"
            )],
            raw_content=''
        )

    # Name
    if info.get('name'):
        doc.fields['name'] = Field(
            name='name',
            is_list=False,
            values=[FieldValue(value=info['name'])],
            raw_content=''
        )

    # Bio
    if info.get('bio'):
        lines = [line.strip() for line in info['bio'].split('\n') if line.strip()]
        if lines:
            doc.fields['bio'] = Field(
                name='bio',
                is_list=False,
                values=[FieldValue(
                    value='',
                    is_array=True,
                    array_values=lines
                )],
                raw_content=''
            )

    # Mobile
    if info.get('mobile'):
        doc.fields['mobile'] = Field(
            name='mobile',
            is_list=False,
            values=[FieldValue(value=info['mobile'])],
            raw_content=''
        )

    # Activity (empty list)
    doc.fields['activity'] = Field(
        name='activity',
        is_list=False,
        values=[FieldValue(
            value='',
            is_array=True,
            array_values=[]
        )],
        raw_content=''
    )

    # Invite
    if info.get('invite_link'):
        doc.fields['invite'] = Field(
            name='invite',
            is_list=False,
            values=[FieldValue(info['invite_link'], is_raw_url=True)],
            raw_content=''
        )

    # Only for channels/groups, not users
    entity = info.get('entity')
    joined = None
    if not isinstance(entity, User):
        if info.get('joined_date'): joined = info['joined_date']
        doc.fields['joined'] = Field(
            name='joined',
            is_list=False,
            values=[FieldValue(value=joined if joined else 'DATE')],
            raw_content=''
        )

        # Created
        if info.get('created_date'):
            entity_id = info['id']
            msg_id = info.get('created_msg_id', 1)
            created_link = f"https://t.me/c/{entity_id}/{msg_id}"

            if msg_id == 1:
                doc.fields['created'] = Field(
                    name='created',
                    is_list=False,
                    values=[FieldValue(
                        value=info['created_date'],
                        details=f"[link]({created_link})"
                    )],
                    raw_content=''
                )
            else:
                if info.get('is_migrated'):
                    value = f"before {info['created_date']}"
                    details = f"migrated, [link]({created_link})"
                else:
                    value = f"before {info['created_date']}"
                    details = f"[link]({created_link})"

                doc.fields['created'] = Field(
                    name='created',
                    is_list=False,
                    values=[FieldValue(
                        value=value,
                        details=details,
                        is_raw=True
                    )],
                    raw_content=''
                )
        else:
            doc.fields['created'] = Field(
                name='created',
                is_list=False,
                values=[FieldValue('DATE')],
                raw_content=''
            )

    # Linked channel (for supergroups)
    if isinstance(entity, Channel) and entity.megagroup:
        if info.get('linked_chat_id'):
            doc.fields['linked channel'] = Field(
                name='linked channel',
                is_list=False,
                values=[FieldValue(
                    value=f"tg_{info['linked_chat_id']}",
                    is_wiki_link=True,
                    wiki_link=f"tg_{info['linked_chat_id']}"
                )],
                raw_content=''
            )

    # Members/Subscribers
    if info.get('count'):
        if isinstance(entity, Channel):
            if entity.megagroup:
                count_field = "members"
            elif entity.broadcast:
                count_field = "subscribers"
            else:
                count_field = "members"
        elif isinstance(entity, Chat):
            count_field = "members"
        else:
            count_field = {"channel": "subscribers", "group": "members"}.get(info.get("type"))

        if count_field:
            doc.fields[count_field] = Field(
                name=count_field,
                is_list=True,
                values=[FieldValue(
                    value=str(info['count']),
                    date=now_date,
                    time=now_time
                )],
                raw_content=''
            )

    # Discussion (for channels)
    if isinstance(entity, Channel) and entity.broadcast:
        if info.get('linked_chat_id'):
            doc.fields['discussion'] = Field(
                name='discussion',
                is_list=False,
                values=[FieldValue(
                    value=f"tg_{info['linked_chat_id']}",
                    is_wiki_link=True,
                    wiki_link=f"tg_{info['linked_chat_id']}"
                )],
                raw_content=''
            )

    # Owner
    if info.get('owner'):
        doc.fields['owner'] = Field(
            name='owner',
            is_list=False,
            values=[FieldValue(
                value=f"tg_{info['owner']}",
                is_wiki_link=True,
                wiki_link=f"tg_{info['owner']}"
            )],
            raw_content=''
        )

    # Admins - Liste MDML avec wikilinks
    if info.get('admins'):
        admin_values = []
        for uid in info['admins']:
            admin_values.append(FieldValue(
                value=f"tg_{uid}",
                is_wiki_link=True,
                wiki_link=f"tg_{uid}"
            ))

        doc.fields['admins'] = Field(
            name='admins',
            is_list=True,
            values=admin_values,
            raw_content=''
        )

    # Discovered
    # if join < discovered: discovered := join else discovered := now
    discovered = now
    if joined and joined < discovered:
        discovered = joined
    doc.fields['discovered'] = Field(
        name='discovered',
        is_list=False,
        values=[FieldValue(value=discovered)],
        raw_content=''
    )

    return doc
