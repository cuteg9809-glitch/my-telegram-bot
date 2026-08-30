import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_NAME = os.getenv("BOT_NAME", "Amazongc").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

DEFAULT_CHANNELS = ["@primeloote", "@primebackp", "@sheinstockprime", "@pexoearner"]
CHANNELS = [x.strip() for x in os.getenv("CHANNELS", ",".join(DEFAULT_CHANNELS)).split(",") if x.strip()]

REFERRAL_POINTS = int(os.getenv("REFERRAL_POINTS", "1"))
REWARD_COST = int(os.getenv("REWARD_COST", "10"))
REWARD_NAME = os.getenv("REWARD_NAME", "Amazon Gift Card")
DB_PATH = os.getenv("DB_PATH", "bot.db")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        points INTEGER DEFAULT 0, referred_by INTEGER, verified INTEGER DEFAULT 0,
        created_at TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS referrals(
        referred_user INTEGER PRIMARY KEY, referrer_user INTEGER, rewarded INTEGER DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, reward_name TEXT,
        cost INTEGER, status TEXT DEFAULT 'pending', reward_code TEXT DEFAULT '',
        created_at TEXT, fulfilled_at TEXT DEFAULT '')""")
    conn.commit()
    return conn

def now():
    return datetime.utcnow().isoformat(timespec="seconds")

def ensure_user(user):
    conn = db()
    conn.execute("""INSERT OR IGNORE INTO users
        (user_id, username, first_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)""",
        (user.id, user.username or "", user.first_name or "", now(), now()))
    conn.execute("UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?",
                 (user.username or "", user.first_name or "", now(), user.id))
    conn.commit(); conn.close()

def get_points(user_id):
    conn = db()
    row = conn.execute("SELECT points FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

def is_verified(user_id):
    conn = db()
    row = conn.execute("SELECT verified FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row[0])

def set_verified(user_id, value):
    conn = db()
    conn.execute("UPDATE users SET verified=?, updated_at=? WHERE user_id=?",
                 (1 if value else 0, now(), user_id))
    conn.commit(); conn.close()

def save_referral(user_id, referrer_id):
    if user_id == referrer_id: return
    conn = db()
    existing = conn.execute("SELECT referred_by FROM users WHERE user_id=?", (user_id,)).fetchone()
    if existing and existing[0]:
        conn.close(); return
    conn.execute("UPDATE users SET referred_by=?, updated_at=? WHERE user_id=?",
                 (referrer_id, now(), user_id))
    conn.execute("INSERT OR IGNORE INTO referrals(referred_user, referrer_user, rewarded) VALUES(?,?,0)",
                 (user_id, referrer_id))
    conn.commit(); conn.close()

def reward_referrer_if_needed(user_id):
    conn = db()
    row = conn.execute("SELECT referrer_user, rewarded FROM referrals WHERE referred_user=?", (user_id,)).fetchone()
    if row and row[0] and not row[1]:
        conn.execute("UPDATE users SET points=points+?, updated_at=? WHERE user_id=?",
                     (REFERRAL_POINTS, now(), row[0]))
        conn.execute("UPDATE referrals SET rewarded=1 WHERE referred_user=?", (user_id,))
        conn.commit()
    conn.close()

def remove_referral_reward(user_id):
    conn = db()
    row = conn.execute("SELECT referrer_user, rewarded FROM referrals WHERE referred_user=?", (user_id,)).fetchone()
    if row and row[0] and row[1]:
        conn.execute("UPDATE users SET points=MAX(points-?,0), updated_at=? WHERE user_id=?",
                     (REFERRAL_POINTS, now(), row[0]))
        conn.execute("UPDATE referrals SET rewarded=0 WHERE referred_user=?", (user_id,))
        conn.commit()
    conn.close()

async def check_channel_membership(context, user_id):
    missing = []
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                missing.append(channel)
        except Exception as e:
            log.warning("Could not check %s: %s", channel, e)
            missing.append(channel)
    return missing

def channel_keyboard(missing=None):
    buttons = []
    for ch in (missing if missing is not None else CHANNELS):
        label = ch if ch.startswith("@") else str(ch)
        buttons.append([InlineKeyboardButton(f"📢 Join {label}", url=f"https://t.me/{label.lstrip('@')}")])
    buttons.append([InlineKeyboardButton("✅ Verify Join", callback_data="verify")])
    buttons.append([
        InlineKeyboardButton("💰 My Points", callback_data="points"),
        InlineKeyboardButton("🎁 Rewards", callback_data="rewards")
    ])
    buttons.append([InlineKeyboardButton("🔗 My Referral", callback_data="referral")])
    return InlineKeyboardMarkup(buttons)

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 My Points", callback_data="points"),
         InlineKeyboardButton("🎁 Rewards", callback_data="rewards")],
        [InlineKeyboardButton("🔗 My Referral", callback_data="referral")]
    ])

def welcome_text(user, missing=None):
    name = user.first_name or "there"
    if missing:
        return (f"💰 <b>Verification Required</b>\n\nHello {name}!\n"
                f"Join all required channels to continue:\n\n" +
                "\n".join(f"• {c}" for c in missing) +
                "\n\nAfter joining, tap <b>✅ Verify Join</b>.")
    return (f"🎉 <b>{BOT_NAME}</b>\n\nWelcome, {name}!\n"
            f"Your verification is complete ✅\n\n"
            f"💰 Points: <b>{get_points(user.id)}</b>\n\nChoose an option below.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_") and arg[4:].isdigit():
            save_referral(user.id, int(arg[4:]))
    missing = await check_channel_membership(context, user.id)
    if missing:
        set_verified(user.id, False)
        remove_referral_reward(user.id)
        await update.message.reply_text(welcome_text(user, missing), parse_mode="HTML",
                                        reply_markup=channel_keyboard(missing))
        return
    if not is_verified(user.id):
        set_verified(user.id, True)
        reward_referrer_if_needed(user.id)
    await update.message.reply_text(welcome_text(user), parse_mode="HTML", reply_markup=menu_keyboard())

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking membership…")
    user = query.from_user
    ensure_user(user)
    missing = await check_channel_membership(context, user.id)
    if missing:
        set_verified(user.id, False); remove_referral_reward(user.id)
        await query.edit_message_text("❌ <b>Verification failed.</b>\n\nJoin these channels and try again:\n" +
                                      "\n".join(f"• {c}" for c in missing) +
                                      "\n\nThen tap <b>Verify Join</b>.",
                                      parse_mode="HTML", reply_markup=channel_keyboard(missing))
        return
    set_verified(user.id, True); reward_referrer_if_needed(user.id)
    await query.edit_message_text(f"✅ <b>Verification successful!</b>\n\nWelcome to {BOT_NAME}.\n"
                                  f"💰 Your points: <b>{get_points(user.id)}</b>",
                                  parse_mode="HTML", reply_markup=menu_keyboard())

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; ensure_user(user)
    text = f"💰 <b>Your Points</b>\n\nPoints: <b>{get_points(user.id)}</b>\n\nInvite friends to earn more."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=menu_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=menu_keyboard())

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; ensure_user(user)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user.id}"
    text = ("🔗 <b>Your Referral Link</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"💰 Current points: <b>{get_points(user.id)}</b>\n"
            f"Earn {REFERRAL_POINTS} point(s) for each successful verified referral.")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=menu_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=menu_keyboard())

async def rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; ensure_user(user)
    p = get_points(user.id)
    conn = db()
    pending = conn.execute("SELECT COUNT(*) FROM claims WHERE user_id=? AND status='pending'", (user.id,)).fetchone()[0]
    conn.close()
    text = (f"🎁 <b>Rewards</b>\n\n"
            f"Reward: <b>{REWARD_NAME}</b>\n"
            f"Cost: <b>{REWARD_COST} points</b>\n"
            f"Your points: <b>{p}</b>\n"
            f"Pending claims: <b>{pending}</b>\n\n"
            "You can submit a claim when you have enough points.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Claim Reward", callback_data="claim")],
        [InlineKeyboardButton("💰 My Points", callback_data="points"),
         InlineKeyboardButton("🔗 My Referral", callback_data="referral")]
    ])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user = query.from_user; ensure_user(user)
    if not is_verified(user.id):
        await query.answer("Please verify your channel membership first.", show_alert=True); return
    conn = db()
    pending = conn.execute("SELECT COUNT(*) FROM claims WHERE user_id=? AND status='pending'", (user.id,)).fetchone()[0]
    points = conn.execute("SELECT points FROM users WHERE user_id=?", (user.id,)).fetchone()[0]
    if pending:
        conn.close()
        await query.answer("You already have a pending claim.", show_alert=True); return
    if points < REWARD_COST:
        conn.close()
        await query.answer(f"You need {REWARD_COST} points. You have {points}.", show_alert=True); return
    conn.execute("UPDATE users SET points=points-?, updated_at=? WHERE user_id=?", (REWARD_COST, now(), user.id))
    cur = conn.execute("INSERT INTO claims(user_id,reward_name,cost,status,created_at) VALUES(?,?,?,?,?)",
                       (user.id, REWARD_NAME, REWARD_COST, "pending", now()))
    claim_id = cur.lastrowid
    conn.commit(); conn.close()
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(admin, f"🎁 <b>New Reward Claim #{claim_id}</b>\n"
                                      f"User: <code>{user.id}</code>\n"
                                      f"Username: @{user.username if user.username else 'none'}\n"
                                      f"Reward: {REWARD_NAME}\nCost: {REWARD_COST}\n\n"
                                      f"Approve: /approve {claim_id} YOUR_REWARD_CODE",
                                      parse_mode="HTML")
        except Exception: pass
    await query.edit_message_text(f"✅ <b>Claim submitted!</b>\n\nClaim ID: <code>#{claim_id}</code>\n"
                                  f"Reward: {REWARD_NAME}\n\nAn admin will review and fulfill your claim.",
                                  parse_mode="HTML", reply_markup=menu_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 <b>{BOT_NAME}</b>\n\n/start - Start\n/points - Points\n/refer - Referral link\n"
        "/rewards - Rewards\n/help - Help\n\n"
        f"🎁 {REWARD_NAME} costs {REWARD_COST} points.",
        parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    conn = db()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    verified = conn.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
    total_points = conn.execute("SELECT COALESCE(SUM(points),0) FROM users").fetchone()[0]
    claims = conn.execute("SELECT COUNT(*) FROM claims WHERE status='pending'").fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 <b>Bot Stats</b>\n\nUsers: {users}\nVerified: {verified}\n"
                                    f"Total points: {total_points}\nPending claims: {claims}", parse_mode="HTML")

async def claims(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    conn = db()
    rows = conn.execute("""SELECT id,user_id,reward_name,cost,created_at FROM claims
                           WHERE status='pending' ORDER BY id DESC LIMIT 20""").fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("No pending claims."); return
    text = "🎁 <b>Pending Claims</b>\n\n"
    for cid, uid, reward, cost, created in rows:
        text += f"#{cid} — User <code>{uid}</code> — {reward} — {cost} pts\n"
    text += "\nApprove: /approve CLAIM_ID REWARD_CODE"
    await update.message.reply_text(text, parse_mode="HTML")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /approve CLAIM_ID REWARD_CODE"); return
    try: claim_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid claim ID."); return
    reward_code = " ".join(context.args[1:]).strip()
    conn = db()
    row = conn.execute("SELECT user_id,reward_name,status FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not row:
        conn.close(); await update.message.reply_text("Claim not found."); return
    uid, reward, status = row
    if status != "pending":
        conn.close(); await update.message.reply_text("Claim is already processed."); return
    conn.execute("UPDATE claims SET status='fulfilled', reward_code=?, fulfilled_at=? WHERE id=?",
                 (reward_code, now(), claim_id))
    conn.commit(); conn.close()
    try:
        await context.bot.send_message(uid, f"🎉 <b>Reward fulfilled!</b>\n\n"
                                  f"Reward: {reward}\nClaim: #{claim_id}\n\n"
                                  f"Your reward code:\n<code>{reward_code}</code>",
                                  parse_mode="HTML")
    except Exception as e:
        log.warning("Could not DM reward to user %s: %s", uid, e)
    await update.message.reply_text(f"✅ Claim #{claim_id} fulfilled.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    message = update.message.text.partition(" ")[2].strip()
    if not message:
        await update.message.reply_text("Usage: /broadcast your message"); return
    conn = db(); ids = [r[0] for r in conn.execute("SELECT user_id FROM users").fetchall()]; conn.close()
    sent = 0
    for uid in ids:
        try:
            await context.bot.send_message(uid, message); sent += 1
        except Exception: pass
    await update.message.reply_text(f"Broadcast finished. Sent: {sent}")

async def post_init(application: Application):
    db()
    me = await application.bot.get_me()
    log.info("Bot started as @%s", me.username)
    log.info("Required channels: %s", CHANNELS)

def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN environment variable is missing.")
    if not CHANNELS: raise RuntimeError("CHANNELS environment variable is missing.")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("refer", referral))
    app.add_handler(CommandHandler("rewards", rewards))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("claims", claims))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(verify, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(points, pattern="^points$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(rewards, pattern="^rewards$"))
    app.add_handler(CallbackQueryHandler(claim, pattern="^claim$"))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
