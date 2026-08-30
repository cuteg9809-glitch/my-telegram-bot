# Amazongc Telegram Bot

Railway-ready Telegram bot with:
- Force-join verification for 4 channels
- Referral links and points
- Reward catalog/claim flow
- Admin claim approval
- Admin stats and broadcast
- SQLite database

## Required Railway Variables

BOT_TOKEN=your_BotFather_token
BOT_NAME=Amazongc
CHANNELS=@primeloote,@primebackp,@sheinstockprime,@pexoearner
ADMIN_IDS=YOUR_TELEGRAM_USER_ID

Optional:
REFERRAL_POINTS=1
REWARD_COST=10
REWARD_NAME=Amazon Gift Card
DB_PATH=bot.db

## Important
Make the bot an administrator in all required channels so Telegram membership checks can work.

## Admin commands
/stats
/claims
/approve CLAIM_ID REWARD_CODE
/broadcast MESSAGE

## User commands
/start
/points
/refer
/rewards
/help

## Reward safety
This version does not generate fake gift-card codes or connect to Amazon automatically.
A genuine reward code must be supplied by an authorized admin using /approve.
