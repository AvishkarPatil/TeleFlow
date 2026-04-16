from __future__ import annotations

from pyrogram import filters, enums
from pyrogram.errors import MessageNotModified
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.client import bot
from bot.filters import sudo
from db import users as user_db
from db.models import ThumbMode, UserPrefs
from utils.formatting import format_bytes, truncate
from logging_config import get_logger

log = get_logger(__name__)

_AWAITING: dict[int, str] = {}
_PM = enums.ParseMode.HTML

_THUMB_LABEL = {
    ThumbMode.ORIGINAL: "Original",
    ThumbMode.CUSTOM:   "Custom",
    ThumbMode.NONE:     "None",
}


async def _edit(cb: CallbackQuery, text: str, **kwargs) -> None:
    try:
        await cb.message.edit_text(text, parse_mode=_PM, **kwargs)
    except MessageNotModified:
        pass


# ── Keyboards ─────────────────────────────────────────────────────────────────


def _settings_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤  ᴅᴇꜱᴛɪɴᴀᴛɪᴏɴ", callback_data="s:dest")],
        [InlineKeyboardButton("🖼  ᴛʜᴜᴍʙɴᴀɪʟ",    callback_data="s:thumb")],
        [InlineKeyboardButton("📝  ꜰɪʟᴇɴᴀᴍᴇ",      callback_data="s:fname")],
        [InlineKeyboardButton("💬  ᴄᴀᴘᴛɪᴏɴ",       callback_data="s:caption")],
        [InlineKeyboardButton("‹  ʙᴀᴄᴋ",           callback_data="back_start")],
    ])


def _dest_kb(has_dest: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_dest:
        rows += [
            [InlineKeyboardButton("✏️  ᴄʜᴀɴɢᴇ", callback_data="s:dest:set")],
            [InlineKeyboardButton("✕  ʀᴇᴍᴏᴠᴇ",  callback_data="s:dest:clear")],
        ]
    else:
        rows.append([InlineKeyboardButton("➕  ꜱᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data="s:dest:set")])
    rows.append([InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="s:main")])
    return InlineKeyboardMarkup(rows)


def _thumb_kb(prefs: UserPrefs) -> InlineKeyboardMarkup:
    m = prefs.thumbnail_mode
    dot = lambda mode: "●" if m == mode else "○"
    rows = [[
        InlineKeyboardButton(f"{dot(ThumbMode.ORIGINAL)}  ᴏʀɪɢɪɴᴀʟ", callback_data="s:thumb:original"),
        InlineKeyboardButton(f"{dot(ThumbMode.NONE)}  ɴᴏɴᴇ",          callback_data="s:thumb:none"),
    ]]
    if prefs.thumbnail_file_id:
        rows.append([
            InlineKeyboardButton(f"{dot(ThumbMode.CUSTOM)}  ᴄᴜꜱᴛᴏᴍ", callback_data="s:thumb:custom"),
            InlineKeyboardButton("✕  ʀᴇᴍᴏᴠᴇ", callback_data="s:thumb:remove"),
        ])
    else:
        rows.append([InlineKeyboardButton("⬆️  ᴜᴘʟᴏᴀᴅ ᴛʜᴜᴍʙ", callback_data="s:thumb:upload")])
    rows.append([InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="s:main")])
    return InlineKeyboardMarkup(rows)


def _fname_kb(has: bool) -> InlineKeyboardMarkup:
    rows = (
        [[InlineKeyboardButton("✏️  ᴇᴅɪᴛ", callback_data="s:fname:set")],
         [InlineKeyboardButton("✕  ʀᴇꜱᴇᴛ", callback_data="s:fname:clear")]]
        if has else
        [[InlineKeyboardButton("➕  ꜱᴇᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data="s:fname:set")]]
    )
    rows.append([InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="s:main")])
    return InlineKeyboardMarkup(rows)


def _caption_kb(prefs: UserPrefs) -> InlineKeyboardMarkup:
    rows = (
        [[InlineKeyboardButton("✏️  ᴇᴅɪᴛ ᴛᴇᴍᴘʟᴀᴛᴇ",   callback_data="s:caption:set")],
         [InlineKeyboardButton("✕  ʀᴇᴍᴏᴠᴇ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data="s:caption:clear")]]
        if prefs.caption_template is not None else
        [[InlineKeyboardButton("➕  ꜱᴇᴛ ᴛᴇᴍᴘʟᴀᴛᴇ", callback_data="s:caption:set")]]
    )
    rows.append([InlineKeyboardButton("＋  ᴀᴅᴅ ꜰɪʟᴛᴇʀ ᴡᴏʀᴅ", callback_data="s:caption:addfilter")])
    if prefs.caption_filters:
        rows.append([InlineKeyboardButton("✕  ᴄʟᴇᴀʀ ꜰɪʟᴛᴇʀꜱ", callback_data="s:caption:clearfilters")])
    rows.append([InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="s:main")])
    return InlineKeyboardMarkup(rows)


def _cancel_kb(back: str = "s:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✕  ᴄᴀɴᴄᴇʟ", callback_data=back)]])


# ── Text builders ─────────────────────────────────────────────────────────────


async def _main_text(user_id: int) -> str:
    user = await user_db.get_user(user_id)
    p = user.prefs if user else UserPrefs()
    tasks_done = user.total_tasks if user else 0
    data_saved = format_bytes(user.total_bytes_transferred) if user else "0 B"

    dest = f"<b>{p.dest_channel_title}</b>" if p.dest_channel_id else "<i>This chat</i>"
    thumb = "Custom ✓" if (p.thumbnail_mode == ThumbMode.CUSTOM and p.thumbnail_file_id) \
            else _THUMB_LABEL.get(p.thumbnail_mode, p.thumbnail_mode)
    fname = f"<code>{truncate(p.filename_template, 28)}</code>" if p.filename_template else "<i>Original</i>"
    caption = f"<code>{truncate(p.caption_template, 28)}</code>" if p.caption_template is not None \
              else "<i>Original</i>"
    filters_n = len(p.caption_filters)
    filters_val = f"<code>{filters_n} word{'s' if filters_n != 1 else ''}</code>" if filters_n else "<i>None</i>"

    return (
        "<b>Settings</b>\n"
        "\n"
        f"•  <b>Destination :</b>  {dest}\n"
        f"•  <b>Thumbnail :</b>    {thumb}\n"
        f"•  <b>Filename :</b>     {fname}\n"
        f"•  <b>Caption :</b>      {caption}\n"
        f"•  <b>Filters :</b>      {filters_val}\n"
        "\n"
        "<code>─────────────────────</code>\n"
        f"•  <b>Tasks :</b>  <code>{tasks_done}</code>   ·   <b>Data :</b>  <code>{data_saved}</code>"
    )


def _dest_text(prefs: UserPrefs) -> str:
    if prefs.dest_channel_id:
        return (
            "📤  <b>Destination</b>\n"
            "\n"
            f"  <b>{prefs.dest_channel_title or 'Unknown'}</b>\n"
            f"  <code>{prefs.dest_channel_id}</code>\n"
            "\n"
            "<i>Files will be forwarded to this channel.</i>"
        )
    return (
        "📤  <b>Destination</b>\n"
        "\n"
        "  <i>Not set — files go to this chat.</i>\n"
        "\n"
        "Forward any message from your target\n"
        "channel to set it as the destination."
    )


def _thumb_text(prefs: UserPrefs) -> str:
    desc = {
        ThumbMode.ORIGINAL: "Use the original thumbnail from the source.",
        ThumbMode.CUSTOM:   "Use your uploaded custom thumbnail.",
        ThumbMode.NONE:     "Send files without any thumbnail.",
    }
    custom_status = "✓  Custom thumbnail saved." if prefs.thumbnail_file_id \
                    else "No custom thumbnail uploaded yet."
    return (
        "<b>Thumbnail</b>\n"
        "\n"
        f"•  <b>Mode :</b>    <b>{_THUMB_LABEL.get(prefs.thumbnail_mode)}</b>\n"
        f"•  <b>Status :</b>  {custom_status}\n"
        "\n"
        f"<i>{desc.get(prefs.thumbnail_mode, '')}</i>"
    )


def _fname_text(prefs: UserPrefs) -> str:
    current = f"<code>{prefs.filename_template}</code>" if prefs.filename_template \
              else "<i>Not set — original filename kept.</i>"
    return (
        "<b>Filename Template</b>\n"
        "\n"
        f"•  <b>Current :</b>  {current}\n"
        "\n"
        "<b>Placeholders</b>\n"
        "•  <code>{filename}</code>  —  original name\n"
        "•  <code>{ext}</code>       —  extension\n"
        "•  <code>{date}</code>      —  YYYY-MM-DD\n"
        "•  <code>{id}</code>        —  task ID\n"
        "•  <code>{chat}</code>      —  source chat\n"
        "\n"
        "<i>Example :</i>  <code>{chat} - {filename}</code>"
    )


def _caption_text(prefs: UserPrefs) -> str:
    current = f"<code>{truncate(prefs.caption_template, 50)}</code>" \
              if prefs.caption_template is not None \
              else "<i>Not set — original caption kept.</i>"
    words = "\n".join(f"•  <code>{w}</code>" for w in prefs.caption_filters) \
            if prefs.caption_filters else "<i>None</i>"
    return (
        "<b>Caption</b>\n"
        "\n"
        f"•  <b>Template :</b>  {current}\n"
        "\n"
        "<b>Filter words</b>  <i>(stripped from captions)</i>\n"
        f"{words}\n"
        "\n"
        "<b>Placeholders</b>\n"
        "•  <code>{caption}</code>   —  original caption\n"
        "•  <code>{filename}</code>  —  file name\n"
        "•  <code>{date}</code>      —  YYYY-MM-DD"
    )


# ── Command ───────────────────────────────────────────────────────────────────


@bot.on_message(sudo & filters.command("settings"))
async def cmd_settings(_: object, message: Message) -> None:
    await message.reply(await _main_text(message.from_user.id),
                        reply_markup=_settings_main_kb(), parse_mode=_PM)


# ── Callbacks ─────────────────────────────────────────────────────────────────


@bot.on_callback_query(filters.regex(r"^s:main$"))
async def cb_s_main(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    _AWAITING.pop(cb.from_user.id, None)
    await _edit(cb, await _main_text(cb.from_user.id), reply_markup=_settings_main_kb())


@bot.on_callback_query(filters.regex(r"^s:dest$"))
async def cb_s_dest(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _dest_text(prefs), reply_markup=_dest_kb(bool(prefs.dest_channel_id)))


@bot.on_callback_query(filters.regex(r"^s:dest:set$"))
async def cb_s_dest_set(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    _AWAITING[cb.from_user.id] = "dest"
    await _edit(cb,
        "📤  <b>Set Destination</b>\n\n"
        "Forward any message from the channel\n"
        "you want files delivered to.\n\n"
        "<i>Make sure I'm an admin in that channel.</i>",
        reply_markup=_cancel_kb("s:dest"),
    )


@bot.on_callback_query(filters.regex(r"^s:dest:clear$"))
async def cb_s_dest_clear(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await user_db.update_prefs(cb.from_user.id, dest_channel_id=None, dest_channel_title=None)
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _dest_text(prefs), reply_markup=_dest_kb(False))


@bot.on_callback_query(filters.regex(r"^s:thumb$"))
async def cb_s_thumb(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _thumb_text(prefs), reply_markup=_thumb_kb(prefs))


@bot.on_callback_query(filters.regex(r"^s:thumb:(original|none|custom)$"))
async def cb_s_thumb_mode(_: object, cb: CallbackQuery) -> None:
    mode = cb.matches[0].group(1)
    prefs = await user_db.get_prefs(cb.from_user.id)
    if mode == ThumbMode.CUSTOM and not prefs.thumbnail_file_id:
        await cb.answer("Upload a thumbnail first.", show_alert=True)
        return
    await user_db.update_prefs(cb.from_user.id, thumbnail_mode=mode)
    await cb.answer(f"Mode set to {mode}.")
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _thumb_text(prefs), reply_markup=_thumb_kb(prefs))


@bot.on_callback_query(filters.regex(r"^s:thumb:upload$"))
async def cb_s_thumb_upload(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    _AWAITING[cb.from_user.id] = "thumb"
    await _edit(cb,
        "🖼  <b>Upload Thumbnail</b>\n\n"
        "Send a photo to use as the default\n"
        "thumbnail for all transferred files.",
        reply_markup=_cancel_kb("s:thumb"),
    )


@bot.on_callback_query(filters.regex(r"^s:thumb:remove$"))
async def cb_s_thumb_remove(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await user_db.update_prefs(cb.from_user.id, thumbnail_file_id=None, thumbnail_mode=ThumbMode.ORIGINAL)
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _thumb_text(prefs), reply_markup=_thumb_kb(prefs))


@bot.on_callback_query(filters.regex(r"^s:fname$"))
async def cb_s_fname(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _fname_text(prefs), reply_markup=_fname_kb(bool(prefs.filename_template)))


@bot.on_callback_query(filters.regex(r"^s:fname:set$"))
async def cb_s_fname_set(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    _AWAITING[cb.from_user.id] = "fname"
    await _edit(cb,
        "📝  <b>Filename Template</b>\n\n"
        "Type your template.\n"
        "Placeholders: <code>{filename}</code> <code>{ext}</code> <code>{date}</code> <code>{id}</code> <code>{chat}</code>\n\n"
        "<i>Example:</i>  <code>{chat} - {filename}</code>",
        reply_markup=_cancel_kb("s:fname"),
    )


@bot.on_callback_query(filters.regex(r"^s:fname:clear$"))
async def cb_s_fname_clear(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await user_db.update_prefs(cb.from_user.id, filename_template=None)
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _fname_text(prefs), reply_markup=_fname_kb(False))


@bot.on_callback_query(filters.regex(r"^s:caption$"))
async def cb_s_caption(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _caption_text(prefs), reply_markup=_caption_kb(prefs))


@bot.on_callback_query(filters.regex(r"^s:caption:set$"))
async def cb_s_caption_set(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    _AWAITING[cb.from_user.id] = "caption"
    await _edit(cb,
        "💬  <b>Caption Template</b>\n\n"
        "Type your caption.\n"
        "Placeholders: <code>{caption}</code> <code>{filename}</code> <code>{date}</code>\n\n"
        "Send <code>-</code> to set an empty caption.",
        reply_markup=_cancel_kb("s:caption"),
    )


@bot.on_callback_query(filters.regex(r"^s:caption:clear$"))
async def cb_s_caption_clear(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await user_db.update_prefs(cb.from_user.id, caption_template=None)
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _caption_text(prefs), reply_markup=_caption_kb(prefs))


@bot.on_callback_query(filters.regex(r"^s:caption:addfilter$"))
async def cb_s_caption_addfilter(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    _AWAITING[cb.from_user.id] = "caption_filter"
    await _edit(cb,
        "✕  <b>Add Filter Word</b>\n\n"
        "Type a word or phrase to automatically\n"
        "strip from all captions.\n\n"
        "<i>Case-insensitive.</i>",
        reply_markup=_cancel_kb("s:caption"),
    )


@bot.on_callback_query(filters.regex(r"^s:caption:clearfilters$"))
async def cb_s_caption_clearfilters(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await user_db.update_prefs(cb.from_user.id, caption_filters=[])
    prefs = await user_db.get_prefs(cb.from_user.id)
    await _edit(cb, _caption_text(prefs), reply_markup=_caption_kb(prefs))


# ── Input handler ─────────────────────────────────────────────────────────────


@bot.on_message(sudo & (filters.text | filters.photo) & ~filters.command([
    "start", "help", "status", "tasks", "cancel",
    "adduser", "removeuser", "users", "settings", "system",
]), group=1)
async def handle_settings_input(_: object, message: Message) -> None:
    uid = message.from_user.id
    state = _AWAITING.get(uid)
    if not state:
        return  # not in settings flow — fall through to messages.py handler

    if state == "dest":
        chat = getattr(message, "forward_from_chat", None)
        if not chat:
            await message.reply("<b><i>⚠️  Forward a message from the target channel.</i></b>",
                                reply_markup=_cancel_kb("s:dest"), parse_mode=_PM)
            return
        _AWAITING.pop(uid, None)
        await user_db.update_prefs(uid, dest_channel_id=chat.id, dest_channel_title=chat.title or str(chat.id))
        await message.reply(f"<b><i>✓  Destination set to {chat.title}</i></b>",
                            reply_markup=_dest_kb(True), parse_mode=_PM)
        log.info("settings.dest_set", user_id=uid, channel_id=chat.id)

    elif state == "thumb":
        if not message.photo:
            await message.reply("<b><i>⚠️  Send a photo.</i></b>", reply_markup=_cancel_kb("s:thumb"), parse_mode=_PM)
            return
        _AWAITING.pop(uid, None)
        await user_db.update_prefs(uid, thumbnail_file_id=message.photo.file_id, thumbnail_mode=ThumbMode.CUSTOM)
        prefs = await user_db.get_prefs(uid)
        await message.reply("<b><i>✓  Thumbnail saved.</i></b>", reply_markup=_thumb_kb(prefs), parse_mode=_PM)

    elif state == "fname":
        text = (message.text or "").strip()
        if not text:
            await message.reply("<b><i>⚠️  Send a valid template.</i></b>", reply_markup=_cancel_kb("s:fname"), parse_mode=_PM)
            return
        _AWAITING.pop(uid, None)
        await user_db.update_prefs(uid, filename_template=text)
        await message.reply(f"<b><i>✓  Template set to</i></b>  <code>{text}</code>",
                            reply_markup=_fname_kb(True), parse_mode=_PM)

    elif state == "caption":
        text = (message.text or "").strip()
        if not text:
            await message.reply("<b><i>⚠️  Send a caption or <code>-</code> for empty.</i></b>",
                                reply_markup=_cancel_kb("s:caption"), parse_mode=_PM)
            return
        _AWAITING.pop(uid, None)
        value = "" if text == "-" else text
        await user_db.update_prefs(uid, caption_template=value)
        label = "<i>empty</i>" if value == "" else f"<code>{truncate(value, 40)}</code>"
        prefs = await user_db.get_prefs(uid)
        await message.reply(f"<b><i>✓  Caption template set to</i></b>  {label}",
                            reply_markup=_caption_kb(prefs), parse_mode=_PM)

    elif state == "caption_filter":
        text = (message.text or "").strip()
        if not text:
            await message.reply("<b><i>⚠️  Send a word or phrase.</i></b>",
                                reply_markup=_cancel_kb("s:caption"), parse_mode=_PM)
            return
        _AWAITING.pop(uid, None)
        prefs = await user_db.get_prefs(uid)
        words = prefs.caption_filters
        if text.lower() not in [w.lower() for w in words]:
            words.append(text)
            await user_db.update_prefs(uid, caption_filters=words)
        prefs = await user_db.get_prefs(uid)
        await message.reply(f"<b><i>✓  Added</i></b>  <code>{text}</code>  <b><i>to filters.</i></b>",
                            reply_markup=_caption_kb(prefs), parse_mode=_PM)
