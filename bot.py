import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

CHANNELS = [
    ("📢 Join @primeloote", "https://t.me/primeloote", "@primeloote"),
    ("📢 Join @primebackp", "https://t.me/primebackp", "@primebackp"),
    ("📢 Join @sheinstockprime", "https://t.me/sheinstockprime", "@sheinstockprime"),
    ("📢 Join @pexoearner", "https://t.me/pexoearner", "@pexoearner"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, url=url)]
        for name, url, username in CHANNELS
    ]

    keyboard.append([
        InlineKeyboardButton("✅ Verify Join", callback_data="verify")
    ])

    text = (
        "💰 AmazonGC Bot\n\n"
        "🎁 Welcome!\n\n"
        "Bot use karne ke liye pehle neeche diye gaye "
        "sabhi channels join karein.\n\n"
        "Join karne ke baad ✅ Verify Join par click karein."
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    not_joined = []

    for name, url, username in CHANNELS:
        try:
            member = await context.bot.get_chat_member(
                chat_id=username,
                user_id=user_id
            )

            if member.status in ["left", "kicked"]:
                not_joined.append((name, url))

        except Exception:
            not_joined.append((name, url))

    if not_joined:
        keyboard = [
            [InlineKeyboardButton(name, url=url)]
            for name, url in not_joined
        ]

        keyboard.append([
            InlineKeyboardButton("🔄 Verify Again", callback_data="verify")
        ])

        await query.edit_message_text(
            "❌ Verification failed.\n\n"
            "Pehle ye required channel(s) join karein, "
            "phir Verify Again dabayein.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await query.edit_message_text(
        "✅ Verification successful!\n\n"
        "🎉 Aapke sabhi required channels join hain.\n\n"
        "💰 AmazonGC Bot is ready to use!"
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable missing")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify, pattern="^verify$"))

    print("AmazonGC Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
