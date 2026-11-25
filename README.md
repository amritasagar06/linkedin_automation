# Daily Interview Article + LinkedIn Approval App

A beginner's setup guide for a cloud based rewrite of the local Streamlit/Ollama app. It selects one interview question each day, drafts an approximately 1,500-word Substack article and a 120–220-word LinkedIn post in the style of examples you provide, sends a Telegram message to your phone, and publishes to LinkedIn only when you approve the exact post.

## Before you start: what changes from the current local app

- **The daily generation runs in GitHub Actions at 2:00 PM Asia/Singapore.** Your PC does not need to be awake or signed in for that scheduled job.
- **Ollama on your PC is not used by the cloud job.** A PC-local model is unavailable when the PC is off. This project uses Gemini API from the cloud. It has a free tier with quotas; Google's current free-tier terms say prompts may be used to improve Google products. For more private production use, select a paid API tier/provider after reviewing its data terms.
- **The question is automatic by default.** The included 99 questions are taken in sequence. The app lets you choose a one-time override for the next daily draft. The attachment heading says 76–100, but the actual file stops after #99.
- **Substack remains a manual step.** Publish the generated article in Substack, paste its public URL into the app, then approve the LinkedIn post. This project does not log into Substack or use unofficial publishing endpoints.
- **LinkedIn posting uses LinkedIn's API.** The phone reminder opens this private review app. After you sign in, paste the Substack link and press **Approve and publish to LinkedIn**. That action sends the post through LinkedIn's API; you do not copy it into LinkedIn yourself.
- **Past-post style matching uses examples you provide.** LinkedIn's `r_member_social` permission for reading a member's post history is closed/restricted, so the app cannot assume it can download your old posts. Paste representative posts into the **Writing style examples** section. The generator uses up to 10 examples in its prompt; it does not train/fine-tune a model.

## How the pieces fit together

| Piece | Job |
|---|---|
| GitHub Actions | Starts the daily cloud generation job at 2:00 PM Singapore time; it is independent of your PC. |
| Gemini API | Drafts the article and LinkedIn adaptation in the cloud. |
| Supabase Postgres | Stores questions, drafts, style examples, approval status, and encrypted LinkedIn tokens. |
| Telegram Bot | Sends a phone notification with a button to open that day's draft. |
| Streamlit Community Cloud | Hosts the password-protected approval page. |
| LinkedIn OAuth + Posts API | Connects your member account and publishes only after your approval. |

The GitHub schedule uses 2:00 PM in `Asia/Singapore`. GitHub says scheduled runs can be delayed during busy periods, so it is a daily target rather than a guaranteed-to-the-minute alarm. The schedule is in `.github/workflows/daily.yml`.

## Files in this folder

```text
LinkedInDailyCloud/
├── README.md                         # This guide
├── app.py                            # Phone-friendly private review / approval UI
├── cloud_common.py                   # Supabase and encrypted-secret helpers
├── daily_job.py                      # Daily question selection, generation, Telegram alert
├── linkedin_api.py                   # OAuth, token renewal when enabled, LinkedIn posting
├── questions.txt                     # Your imported interview question bank
├── schema.sql                        # Tables to create in Supabase
├── requirements.txt                  # Python packages for Streamlit and GitHub Actions
├── telegram_setup.py                 # Safely finds your Telegram chat id
├── privacy.html                      # Simple policy page for LinkedIn app setup
├── .streamlit/secrets.toml.example   # Local example only; never commit secrets.toml
└── .github/workflows/daily.yml       # Daily 2 PM Singapore schedule
```

## Step 1 — Make a new project folder and open it in VS Code

Keep this cloud version in its own folder so your current local Ollama project remains untouched.

1. Download and unzip the `LinkedInDailyCloud` project folder.
2. In VS Code, select **File → Open Folder…** and open `LinkedInDailyCloud`.
3. Select **Terminal → New Terminal**. In the terminal, confirm you are in the folder containing `app.py`:

   ```powershell
   Get-Location
   Get-ChildItem
   ```

   The list should include `app.py`, `daily_job.py`, and `requirements.txt`.

## Step 2 — Install the Python packages and create private local settings

In the VS Code PowerShell terminal, run these commands from the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Open `.streamlit/secrets.toml` in VS Code. You will fill it in as you create the accounts below. This file is ignored by Git. **Never paste passwords, API keys, OAuth tokens, or encryption keys into chat or commit them to GitHub.**

Generate two local secrets in PowerShell. Copy the output somewhere private; put the password in `APP_PASSWORD` and the Fernet key in `TOKEN_ENCRYPTION_KEY` in `.streamlit/secrets.toml`:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Step 3 — Create the Supabase database

1. Create a Supabase account and a new project. Save the database password somewhere private.
2. Open the project's **SQL Editor**, choose **New query**, open this project's `schema.sql`, copy all of it into the editor, and click **Run** once.
3. In **Project Settings → API**, copy the Project URL and the `service_role` key. Put them in `.streamlit/secrets.toml` as `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

   The service-role key can bypass row-level security. This app uses it only on its Python server and in the private GitHub workflow. Never put it in client-side JavaScript, a public repo, a screenshot, or a message.

4. The included `questions.txt` is imported automatically by the first daily job. If you add questions after that, add rows to the Supabase `questions` table using its Table Editor. The in-app question override changes only the next question; normal daily rotation resumes afterwards.

The Supabase Free plan has 500 MB of database storage and can pause a project after a week with too little activity. Daily workflow activity should help, but Supabase does not guarantee that free projects remain active. Upgrade if you need an always-available database.

## Step 4 — Create a Gemini API key for cloud writing

1. In Google AI Studio, create a Gemini API key.
2. Do not use that key in the Streamlit page or commit it. Add it later as a GitHub Actions secret named `GEMINI_API_KEY`.
3. `GEMINI_MODEL` defaults to `gemini-2.5-flash` in the workflow. Check Google's current model list before setup; if that model is no longer available, add a GitHub Actions variable named `GEMINI_MODEL` with a currently supported model ID.

Google's [Gemini API pricing and data terms](https://ai.google.dev/gemini-api/docs/pricing) currently list free usage for selected models, subject to quotas; free-tier content may be used to improve Google products. Paid-tier content is not used for that purpose according to Google's current pricing page. Review the terms before sending drafts or personal examples. If you do not want to use a hosted model, local Ollama is the free alternative, but then the PC must be on and Ollama running at generation time.

## Step 5 — Set up Telegram phone notifications

1. On your phone, install Telegram if you do not already use it.
2. Search for `@BotFather`, open it, send `/newbot`, follow the prompts, and copy the bot token it gives you. Keep it private.
3. Open the new bot using the link BotFather gives you and press **Start** (or send `/start`). A bot cannot message you until you start the conversation.
4. Back in the VS Code terminal, run:

   ```powershell
   .\.venv\Scripts\python.exe telegram_setup.py
   ```

   Paste the bot token when prompted. Input is hidden. The script prints your private Telegram chat ID. Do not send the bot token to anyone.

The scheduled job uses the token and chat ID to send one daily message with a button to your review app. Telegram's Bot API supports sending these messages; low-volume personal notifications are within its normal free limits.

## Step 6 — Create a private GitHub repository and upload the project

GitHub Actions runs the daily job on GitHub's servers. Create a **private empty repository** on GitHub. Do not initialize it with a README, because this folder already contains files.

In VS Code's PowerShell terminal, replace the URL placeholder with your repo URL and run:

```powershell
git init
git add .
git commit -m "Set up daily interview content app"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Before pushing, check that `.streamlit/secrets.toml` is not listed by `git status`. If it is listed, stop and remove it from Git's staged files before pushing. `.gitignore` is configured to ignore that file.

In the GitHub repository, open **Settings → Secrets and variables → Actions** and add these **Repository secrets**:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | Key from Step 4 |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key |
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_CHAT_ID` | Chat ID from Step 5 |

Then add these **Repository variables**:

| Variable name | Value |
|---|---|
| `APP_URL` | Your deployed Streamlit URL; fill this after Step 7, e.g. `https://your-app-name.streamlit.app` |
| `GEMINI_MODEL` | Optional; set only if you need to override the workflow default |

Open **Actions** in GitHub and enable workflows if GitHub asks. Keep the repository private if you do not want the code/question bank public. GitHub Free currently includes 2,000 Actions minutes/month for private repositories; public-repo standard runner time is free. A small daily workflow should use only a fraction of that, but minutes and plan rules can change.

## Step 7 — Deploy the phone approval app to Streamlit Community Cloud

1. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub.
2. Choose **Create app**, select your private repository, branch `main`, and entry file `app.py`, then deploy.
3. In the app's **Advanced settings → Secrets**, add the following TOML values. Use the generated password and Fernet key from Step 2. Replace every placeholder; do not copy the example values literally.

   ```toml
   APP_PASSWORD = "your-long-random-app-password"
   APP_URL = "https://your-app-name.streamlit.app"
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_SERVICE_ROLE_KEY = "your-supabase-service-role-key"
   TOKEN_ENCRYPTION_KEY = "your-generated-fernet-key"
   LINKEDIN_CLIENT_ID = "filled-in-after-step-8"
   LINKEDIN_CLIENT_SECRET = "filled-in-after-step-8"
   LINKEDIN_REDIRECT_URI = "https://your-app-name.streamlit.app"
   LINKEDIN_VERSION = "202610"
   ```

4. Click **Save** to restart the app. Open the URL and sign in with `APP_PASSWORD`.
5. Copy the exact app URL (no extra path) into GitHub's `APP_URL` repository variable from Step 6.

Streamlit Community Cloud is free, but apps go to sleep after 12 hours without traffic. The scheduled GitHub job does not depend on the Streamlit app being awake; opening the Telegram link wakes it. Free hosting is suitable for trying this personal workflow, not a guaranteed uptime service.

## Step 8 — Create and authorize the LinkedIn Developer app

1. Open [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps) and create an app. LinkedIn may require a LinkedIn Page associated with the app. If it asks, select a Page you administer or create a Page. LinkedIn also asks for a privacy-policy URL for app creation. Because your app code repository is private, on GitHub Free create a separate public repository named `interview-content-privacy`, copy only this project's `privacy.html` into it, then enable **Settings → Pages → Deploy from a branch → main / root**. Your privacy URL will look like `https://YOUR-USERNAME.github.io/interview-content-privacy/privacy.html`. You can use any other public HTTPS privacy-policy page instead. GitHub Pages on GitHub Free is available for public repositories.
2. In the app's **Products** tab, add **Share on LinkedIn**. This grants `w_member_social`, the permission for posting on behalf of the signed-in member.
3. Also enable **Sign In with LinkedIn using OpenID Connect** so the app can request `openid profile` and identify the member. The app requests only `openid profile w_member_social`.
4. In the **Auth** tab, add your Streamlit URL as the OAuth redirect URL. It must exactly match `LINKEDIN_REDIRECT_URI` in Streamlit secrets, including whether it ends in `/`.
5. Copy the app's **Client ID** and **Client Secret** into Streamlit Community Cloud secrets. Never put these values in the GitHub repo or in GitHub Actions; LinkedIn OAuth is handled by the Streamlit app.
6. In the deployed app, sign in and press **Connect / reconnect LinkedIn**. LinkedIn opens its own consent screen. Approve the requested permissions; it returns to the app and encrypts the received token in Supabase.

LinkedIn says member access tokens generally last 60 days. The app refreshes them if LinkedIn issues a refresh token. **Programmatic refresh tokens are not available to every app**; LinkedIn documents them for a limited partner set. If your app does not receive one, reconnect LinkedIn when the app reports that its access token is expiring. Therefore an absolute promise of never needing to sign in again is not possible for every LinkedIn developer app. See LinkedIn's [OAuth flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow) and [refresh-token limits](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens).

The official [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api) uses `POST /rest/posts`, the member author URN, and a version header. The app calls this API only after you press the approval/publish button. `w_member_social` is the permission for writing member posts. Automatic reading of your past post history is separate: `r_member_social` is restricted/closed, so this app uses samples you paste in rather than scraping your account.

## Step 9 — Add examples of your writing style

1. Sign in to the deployed app.
2. Expand **Writing style examples**.
3. Paste several of your own past LinkedIn posts, one at a time, and press **Save style example**.
4. Use 5–10 varied posts that sound like the voice you want the model to reproduce. Avoid private messages, confidential work, or other people's posts.

The daily prompt will use up to 10 examples to infer your tone, paragraph length, headings, pacing, and vocabulary. This is prompt-based style conditioning, not model training. With Gemini's free tier, submitted examples may be used to improve Google's products under its current terms; use a paid tier or a provider with terms you prefer if that is not acceptable.

## Step 10 — Run the first daily job and confirm the phone approval path

1. In GitHub, open **Actions → Daily article and LinkedIn draft → Run workflow**. This starts a one-time manual run so you do not need to wait until tomorrow at 2 PM.
2. Confirm the run completes. It creates a draft row in Supabase and sends a Telegram message to your phone.
3. Tap **Open review and approval** in Telegram. Sign in with your app password.
4. Review the article. Publish it manually on Substack and copy its public URL.
5. Paste the Substack URL in the app, save, and review the final LinkedIn copy. Then check the approval box and press **Approve and publish to LinkedIn**.
6. Verify the resulting post on LinkedIn. The app records its result so the same draft is not offered for routine republication.

The daily question is selected automatically. To change only the next scheduled question, expand **Question selection: automatic by default**, choose the question, and press **Set one-time question override**. The following day returns to automatic rotation.

## Step 11 — Understand timing, cost, and service limits

- **Time:** 2:00 PM Singapore time, daily. The workflow file uses the IANA timezone `Asia/Singapore`, so the 2 PM time does not need manual UTC conversion. GitHub notes scheduled runs can be delayed when its Actions service is busy. If execution must be punctual, use a paid cloud scheduler/worker and still keep the approval gate.
- **PC:** It does not need to be powered on or signed in for cloud generation or the Telegram reminder. You need internet and a phone to review/approve. Local Ollama is not part of this cloud run.
- **LinkedIn:** The first OAuth connection requires your consent. Later reauthentication may be required if LinkedIn does not issue a refresh token or revokes it.
- **Substack:** Still manually published. The daily LinkedIn post cannot be approved until its public Substack URL is present.
- **Free limits:** GitHub Actions, Streamlit Community Cloud, Supabase Free, Gemini API Free (selected models/quotas), and Telegram can make a low-volume trial cost $0. None promises production-grade uptime. Supabase Free may pause after a week of low activity; Streamlit Community Cloud sleeps after 12 hours without traffic; GitHub scheduled runs may be delayed; free Gemini limits and data terms can change.
- **Closest more reliable setup:** keep GitHub/Streamlit if the occasional delay is acceptable; upgrade the database/LLM or use an always-on cloud scheduler if you need stronger service guarantees. Cloud inference while your PC is off has an ongoing compute/API cost unless you accept free-tier quotas and trade-offs.

## Troubleshooting

- **GitHub says no questions:** check the Actions log and ensure `questions.txt` was pushed; the first job seeds the Supabase `questions` table.
- **No Telegram message:** make sure you pressed **Start** on your bot and `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `APP_URL` are set in GitHub repository secrets/variables. Re-run the workflow; if the draft already exists, the job sends its review link again.
- **Streamlit cannot connect to Supabase:** verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are in Streamlit Cloud secrets, then reboot the app.
- **LinkedIn says `invalid_scope` or `unauthorized_scope`:** enable the corresponding LinkedIn Products and reconnect. `w_member_social` comes from Share on LinkedIn; OIDC scopes come from Sign In with LinkedIn using OpenID Connect.
- **LinkedIn says redirect URI mismatch:** compare the Auth-tab URL and `LINKEDIN_REDIRECT_URI` character-for-character. They must be the deployed HTTPS Streamlit URL.
- **LinkedIn token expired:** choose **Connect / reconnect LinkedIn** again. The app may not be eligible for background refresh.
- **A post request timed out:** the app marks it `publication_unknown` rather than retrying blindly. Check your LinkedIn profile first; a timeout can happen after LinkedIn accepted the post.
- **Wrong article/style/length:** edit it before publishing; add better style examples. The model output is a draft and can contain technical mistakes.

## Official references

- [LinkedIn Share on LinkedIn and `w_member_social`](https://learn.microsoft.com/linkedin/consumer/integrations/self-serve/share-on-linkedin)
- [LinkedIn OAuth authorization-code flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow)
- [LinkedIn refresh-token availability](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens)
- [LinkedIn Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
- [LinkedIn access to member post history](https://learn.microsoft.com/en-us/linkedin/marketing/lms-faq?view=li-lms-2026-01)
- [GitHub scheduled workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Streamlit Community Cloud and hibernation](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)
- [Supabase free-project pausing and limits](https://supabase.com/docs/guides/platform/free-project-pausing)
- [Gemini API pricing and free-tier data terms](https://ai.google.dev/gemini-api/docs/pricing)
- [Telegram Bot API](https://core.telegram.org/bots/api)
