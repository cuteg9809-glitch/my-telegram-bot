import os
import sqlite3
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Apna Telegram numeric ID Railway Variable ADMIN_ID me daalna.
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

REFERRAL_POINTS = 5
REWARD_COST = 10
REWARD_NAME = "Amazon Gift Card"

CHANNELS = [
    ("📢 Join @primeloote", "https://t.me/primeloote"),
    ("📢 Join @primebackp", "https://t.me/primebackp"),
    ("📢 Join @sheinstockprime", "https://t.me/sheinstockprime"),
    ("📢 Join @pexoearner", "https://t.me/pexoearner"),
]

DB_FILE = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# DATABASE
# =========================

def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            referrals INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reward TEXT,
            points INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    con.commit()
    con.close()


def add_user(user):
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (user.id,)
    )

    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users
            (user_id, username, first_name, points, referrals, verified, created_at)
            VALUES (?, ?, ?, 0, 0, 0, ?)
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            datetime.now().isoformat()
        ))

    else:
        cur.execute("""
            UPDATE users
            SET username=?, first_name=?
            WHERE user_id=?
        """, (
            user.username or "",
            user.first_name or "",
            user.id
        ))

    con.commit()
    con.close()


def get_user(user_id):
    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT user_id, username, first_name, points,
               referred_by, referrals, verified
        FROM users
        WHERE user_id=?
    """, (user_id,))

    result = cur.fetchone()

    con.close()
    return result


# =========================
# CHANNEL VERIFICATION
# =========================

async def check_channels(user_id, context):
    """
    Bot must be ADMIN/member-check capable in required channels.
    """
    for _, link in CHANNELS:
        try:
            username = link.split("/")[-1]

            member = await context.bot.get_chat_member(
                f"@{username}",
                user_id
            )

            if member.status in ["left", "kicked"]:
                return False

        except Exception as e:
            logger.warning("Channel check failed: %s", e)
            return False

    return True


def channel_keyboard():
    buttons = []

    for name, link in CHANNELS:
        buttons.append([
            InlineKeyboardButton(name, url=link)
        ])

    buttons.append([
        InlineKeyboardButton(
            "🔄 Verify Again",
            callback_data="verify"
        )
    ])

    return InlineKeyboardMarkup(buttons)


async def require_verification(update, context):
    user = update.effective_user

    await update.message.reply_text(
        "❌ <b>Verification required</b>\n\n"
        "Pehle ye sabhi required channels join karein.\n"
        "Join karne ke baad <b>Verify Again</b> dabayein.",
        reply_markup=channel_keyboard(),
        parse_mode="HTML"
    )


# =========================
# MAIN MENU
# =========================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎁 Rewards", callback_data="rewards"),
            InlineKeyboardButton("💰 My Points", callback_data="points")
        ],
        [
            InlineKeyboardButton("🔗 My Referral", callback_data="referral")
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="stats")
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ])


async def show_menu(update, context):
    text = (
        "🎉 <b>Welcome to AmazonGC Bot!</b>\n\n"
        "💰 Earn points by referring friends.\n"
        "🎁 Use your points to claim rewards.\n\n"
        "👇 Select an option:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    add_user(user)

    # Referral deep link:
    # /start 123456789
    if context.args:
        try:
            referrer_id = int(context.args[0])

            if referrer_id != user.id:
                con = db()
                cur = con.cursor()

                cur.execute(
                    "SELECT referred_by FROM users WHERE user_id=?",
                    (user.id,)
                )

                row = cur.fetchone()

                if row and row[0] is None:
                    cur.execute("""
                        UPDATE users
                        SET referred_by=?
                        WHERE user_id=?
                    """, (referrer_id, user.id))

                con.commit()
                con.close()

        except ValueError:
            pass

    verified = await check_channels(user.id, context)

    if not verified:
        await update.message.reply_text(
            "❌ <b>Verification failed</b>\n\n"
            "Pehle required channels join karein, "
            "phir Verify Again dabayein.",
            reply_markup=channel_keyboard(),
            parse_mode="HTML"
        )
        return

    # First successful verification
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT verified, referred_by FROM users WHERE user_id=?",
        (user.id,)
    )

    row = cur.fetchone()

    already_verified = row[0]
    referrer_id = row[1]

    if not already_verified:

        cur.execute("""
            UPDATE users
            SET verified=1
            WHERE user_id=?
        """, (user.id,))

        # Give referral points only once.
        if referrer_id:
            cur.execute("""
                UPDATE users
                SET points=points+?,
                    referrals=referrals+1
                WHERE user_id=?
            """, (REFERRAL_POINTS, referrer_id))

    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ <b>Verification successful!</b>\n\n"
        "🎉 Aapke sabhi required channels join hain.\n\n"
        "💰 Ab aap points earn kar sakte hain.\n"
        "🎁 Rewards claim kar sakte hain.\n"
        "🔗 Friends ko refer kar sakte hain.",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )


# =========================
# POINTS
# =========================

async def points(update, context):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    points_value = user[3] if user else 0

    await query.edit_message_text(
        f"💰 <b>My Points</b>\n\n"
        f"⭐ Points: <b>{points_value}</b>\n\n"
        f"🎁 Reward cost: <b>{REWARD_COST} points</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Rewards", callback_data="rewards")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )


# =========================
# REFERRAL
# =========================

async def referral(update, context):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    referrals = user[5] if user else 0

    bot_username = (await context.bot.get_me()).username

    referral_link = (
        f"https://t.me/{bot_username}?start={query.from_user.id}"
    )

    await query.edit_message_text(
        "🔗 <b>My Referral</b>\n\n"
        f"👥 Total referrals: <b>{referrals}</b>\n"
        f"⭐ Points per referral: <b>{REFERRAL_POINTS}</b>\n\n"
        "📨 Your referral link:\n"
        f"<code>{referral_link}</code>\n\n"
        "👆 Link ko friends ke saath share karein.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📤 Share Referral",
                    url=f"https://t.me/share/url?url={referral_link}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Main Menu",
                    callback_data="menu"
                )
            ]
        ]),
        parse_mode="HTML"
    )


# =========================
# REWARDS
# =========================

async def rewards(update, context):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    points_value = user[3] if user else 0

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM claims
        WHERE user_id=? AND status='pending'
    """, (query.from_user.id,))

    pending = cur.fetchone()[0]

    con.close()

    await query.edit_message_text(
        "🎁 <b>Rewards</b>\n\n"
        f"🏆 Reward: <b>{REWARD_NAME}</b>\n"
        f"💰 Cost: <b>{REWARD_COST} points</b>\n"
        f"⭐ Your points: <b>{points_value}</b>\n"
        f"⏳ Pending claims: <b>{pending}</b>\n\n"
        "Claim karne ke liye required points hone chahiye.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎁 Claim Reward",
                    callback_data="claim"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Main Menu",
                    callback_data="menu"
                )
            ]
        ]),
        parse_mode="HTML"
    )


# =========================
# CLAIM
# =========================

async def claim(update, context):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    user = get_user(user_id)

    if not user:
        return

    points_value = user[3]

    if points_value < REWARD_COST:
        await query.answer(
            f"❌ Aapke paas {REWARD_COST} points hone chahiye.",
            show_alert=True
        )
        return

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM claims
        WHERE user_id=? AND status='pending'
    """, (user_id,))

    pending = cur.fetchone()[0]

    if pending > 0:
        con.close()

        await query.answer(
            "⏳ Aapki ek claim already pending hai.",
            show_alert=True
        )
        return

    # Deduct points and create claim.
    cur.execute("""
        UPDATE users
        SET points=points-?
        WHERE user_id=?
    """, (REWARD_COST, user_id))

    cur.execute("""
        INSERT INTO claims
        (user_id, reward, points, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (
        user_id,
        REWARD_NAME,
        REWARD_COST,
        datetime.now().isoformat()
    ))

    claim_id = cur.lastrowid

    con.commit()
    con.close()

    await query.edit_message_text(
        "✅ <b>Claim submitted!</b>\n\n"
        f"🎁 Reward: <b>{REWARD_NAME}</b>\n"
        f"🆔 Claim ID: <code>#{claim_id}</code>\n"
        "⏳ Status: <b>Pending</b>\n\n"
        "Admin approval ke baad reward fulfill kiya jayega.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎁 Rewards",
                    callback_data="rewards"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Main Menu",
                    callback_data="menu"
                )
            ]
        ]),
        parse_mode="HTML"
    )

    # Notify admin.
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                "🔔 <b>New Reward Claim</b>\n\n"
                f"👤 User: {query.from_user.mention_html()}\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"🎁 Reward: <b>{REWARD_NAME}</b>\n"
                f"💰 Cost: <b>{REWARD_COST}</b>\n"
                f"📋 Claim ID: <code>#{claim_id}</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Admin notification failed: %s", e)


# =========================
# STATS
# =========================

async def stats(update, context):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        return

    await query.edit_message_text(
        "📊 <b>My Stats</b>\n\n"
        f"👤 User ID: <code>{user[0]}</code>\n"
        f"⭐ Points: <b>{user[3]}</b>\n"
        f"👥 Referrals: <b>{user[5]}</b>\n"
        f"✅ Verified: <b>{'Yes' if user[6] else 'No'}</b>",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Main Menu",
                    callback_data="menu"
                )
            ]
        ]),
        parse_mode="HTML"
    )


# =========================
# HELP
# =========================

async def help_menu(update, context):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "ℹ️ <b>How to use</b>\n\n"
        "1️⃣ Required channels join karein.\n"
        "2️⃣ Verify Again karein.\n"
        "3️⃣ Referral link share karein.\n"
        f"4️⃣ Har valid referral par {REFERRAL_POINTS} points milenge.\n"
        f"5️⃣ {REWARD_COST} points hone par reward claim karein.\n"
        "6️⃣ Claim admin approval ke baad process hogi.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Main Menu",
                    callback_data="menu"
                )
            ]
        ]),
        parse_mode="HTML"
    )


# =========================
# VERIFY CALLBACK
# =========================

async def verify(update, context):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    verified = await check_channels(user_id, context)

    if not verified:
        await query.answer(
            "❌ Abhi bhi koi required channel missing hai.",
            show_alert=True
        )
        return

    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT verified, referred_by FROM users WHERE user_id=?",
        (user_id,)
    )

    row = cur.fetchone()

    if not row:
        con.close()
        return

    already_verified = row[0]
    referrer_id = row[1]

    if not already_verified:

        cur.execute("""
            UPDATE users
            SET verified=1
            WHERE user_id=?
        """, (user_id,))

        if referrer_id and referrer_id != user_id:
            cur.execute("""
                UPDATE users
                SET points=points+?,
                    referrals=referrals+1
                WHERE user_id=?
            """, (REFERRAL_POINTS, referrer_id))

    con.commit()
    con.close()

    await query.edit_message_text(
        "✅ <b>Verification successful!</b>\n\n"
        "🎉 Aapke sabhi required channels join hain.\n\n"
        "💰 Welcome! Ab bot use kar sakte hain.",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )


# =========================
# ADMIN
# =========================

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


async def admin(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only.")
        return

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT SUM(points) FROM users")
    points_total = cur.fetchone()[0] or 0

    cur.execute(
        "SELECT COUNT(*) FROM claims WHERE status='pending'"
    )
    pending = cur.fetchone()[0]

    con.close()

    await update.message.reply_text(
        "👑 <b>Admin Panel</b>\n\n"
        f"👥 Users: <b>{users}</b>\n"
        f"⭐ Total points: <b>{points_total}</b>\n"
        f"⏳ Pending claims: <b>{pending}</b>\n\n"
        "Commands:\n"
        "/claims - pending claims\n"
        "/stats - bot statistics",
        parse_mode="HTML"
    )


async def admin_claims(update, context):
    if not is_admin(update.effective_user.id):
        return

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT id, user_id, reward, points, created_at
        FROM claims
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = cur.fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("✅ No pending claims.")
        return

    for row in rows:
        claim_id, user_id, reward, points, created = row

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve:{claim_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject:{claim_id}"
                )
            ]
        ])

        await update.message.reply_text(
            f"🆔 Claim: <code>#{claim_id}</code>\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"🎁 Reward: {reward}\n"
            f"💰 Points: {points}\n"
            f"📅 {created}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )


async def admin_stats(update, context):
    if not is_admin(update.effective_user.id):
        return

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE verified=1"
    )
    verified = cur.fetchone()[0]

    cur.execute(
        "SELECT SUM(referrals) FROM users"
    )
    referrals = cur.fetchone()[0] or 0

    cur.execute(
        "SELECT COUNT(*) FROM claims WHERE status='pending'"
    )
    pending = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM claims WHERE status='approved'"
    )
    approved = cur.fetchone()[0]

    con.close()

    await update.message.reply_text(
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: <b>{users}</b>\n"
        f"✅ Verified users: <b>{verified}</b>\n"
        f"🔗 Referrals: <b>{referrals}</b>\n"
        f"⏳ Pending claims: <b>{pending}</b>\n"
        f"✅ Approved claims: <b>{approved}</b>",
        parse_mode="HTML"
    )


# =========================
# ADMIN CLAIM ACTION
# =========================

async def claim_action(update, context):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "❌ Admin only.",
            show_alert=True
                    )
    
