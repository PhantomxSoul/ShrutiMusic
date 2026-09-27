import os
import asyncio
import requests

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ShrutixMusic import nand


def upload_file(file_path):
    url = "https://uguu.se/upload.php"

    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                url,
                files={"files[]": f},
                timeout=300,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
            )

        if response.status_code != 200:
            return False, f"HTTP {response.status_code}: {response.text[:500]}"

        try:
            data = response.json()
        except Exception:
            return False, f"Invalid response from Uguu: {response.text[:500]}"

        if data.get("success") and data.get("files"):
            return True, data["files"][0]["url"]

        return False, str(data)

    except requests.exceptions.Timeout:
        return False, "Upload timed out."

    except Exception as e:
        return False, str(e)


@nand.on_message(
    filters.command(["tgm", "tgt", "telegraph", "tl"])
)
async def get_link_group(client, message):
    if not message.reply_to_message:
        return await message.reply_text(
            "❖ ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇᴅɪᴀ ᴛᴏ ᴜᴘʟᴏᴀᴅ."
        )

    media = message.reply_to_message

    if not (
        media.photo
        or media.video
        or media.document
        or media.animation
        or media.audio
    ):
        return await message.reply_text(
            "❖ ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴀᴜᴅɪᴏ, ᴅᴏᴄᴜᴍᴇɴᴛ ᴏʀ ɢɪғ."
        )

    file_size = 0
    file_name = "media_file"

    if media.photo:
        file_size = media.photo.file_size or 0
        file_name = "photo.jpg"

    elif media.video:
        file_size = media.video.file_size or 0
        file_name = media.video.file_name or "video.mp4"

    elif media.document:
        file_size = media.document.file_size or 0
        file_name = media.document.file_name or "document.file"

    elif media.animation:
        file_size = media.animation.file_size or 0
        file_name = media.animation.file_name or "animation.gif"

    elif media.audio:
        file_size = media.audio.file_size or 0
        file_name = media.audio.file_name or "audio.mp3"

    if file_size > 200 * 1024 * 1024:
        return await message.reply_text(
            "❖ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴍᴇᴅɪᴀ ғɪʟᴇ ᴜɴᴅᴇʀ 200 MB."
        )

    size_mb = round(file_size / (1024 * 1024), 2)

    status = await message.reply_text(
        "❍ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ... 0%"
    )

    local_path = None

    try:
        async def progress(current, total):
            try:
                percent = current * 100 / total
                await status.edit_text(
                    f"❍ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ... {percent:.1f}%"
                )
            except Exception:
                pass

        local_path = await media.download(
            file_name=f"downloads/{file_name}",
            progress=progress,
        )

        await status.edit_text(
            "❍ ᴜᴘʟᴏᴀᴅɪɴɢ ᴛᴏ Uguu.se..."
        )

        success, upload_path = await asyncio.to_thread(
            upload_file,
            local_path,
        )

        if not success:
            return await status.edit_text(
                "❖ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ\n\n"
                f"<code>{upload_path}</code>"
            )

        caption = (
            "<b>𝐔ᴘʟᴏᴀᴅᴇᴅ 𝐒ᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
            f"➤ <b>𝐅ɪʟᴇ:</b> {file_name}\n"
            f"➤ <b>𝐒ɪᴢᴇ:</b> {size_mb} 𝐌𝐁\n"
            "➤ <b>𝐒ᴇʀᴠɪᴄᴇ:</b> Uguu.se\n\n"
            f"🔗 <a href=\"{upload_path}\">{upload_path}</a>"
        )

        await status.edit_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "• 𝐔ɢᴜᴜ 𝐋ɪɴᴋ •",
                            url=upload_path,
                        )
                    ]
                ]
            ),
        )

    except Exception as e:
        await status.edit_text(
            "❖ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ\n\n"
            f"<i>ʀᴇᴀsᴏɴ:</i> <code>{e}</code>"
        )

    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass