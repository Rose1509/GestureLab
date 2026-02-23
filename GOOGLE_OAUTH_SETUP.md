# Google OAuth Setup Instructions

This guide will help you set up Google OAuth authentication for the Gesture Lab application.

## Prerequisites

- A Google account
- Access to Google Cloud Console

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top
3. Click **"New Project"**
4. Enter a project name (e.g., "Gesture Lab OAuth")
5. Click **"Create"**

## Step 2: Enable Google+ API

1. In your project, go to **"APIs & Services"** > **"Library"**
2. Search for **"Google+ API"** or **"Google Identity"**
3. Click on it and press **"Enable"**

## Step 3: Configure OAuth Consent Screen

1. Go to **"APIs & Services"** > **"OAuth consent screen"**
2. Choose **"External"** (unless you have a Google Workspace account)
3. Click **"Create"**
4. Fill in the required information:
   - **App name**: Gesture Lab (or your preferred name)
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
5. Click **"Save and Continue"**
6. On the **Scopes** page, click **"Add or Remove Scopes"**
   - Add: `email`, `profile`, `openid`
   - Click **"Update"** then **"Save and Continue"**
7. On the **Test users** page (for development), add test users if needed
8. Click **"Save and Continue"** and then **"Back to Dashboard"**

## Step 4: Create OAuth 2.0 Credentials

1. Go to **"APIs & Services"** > **"Credentials"**
2. Click **"+ CREATE CREDENTIALS"** > **"OAuth client ID"**
3. Choose **"Web application"** as the application type
4. Fill in the details:
   - **Name**: Gesture Lab OAuth Client (or your preferred name)
   - **Authorized JavaScript origins**:
     - For local development: `http://127.0.0.1:8000`
     - For production: `https://yourdomain.com`
   - **Authorized redirect URIs**:
     - For local development: `http://127.0.0.1:8000/auth/google/callback`
     - For production: `https://yourdomain.com/auth/google/callback`
5. Click **"Create"**
6. **IMPORTANT**: Copy the **Client ID** and **Client Secret** - you'll need these for your `.env` file

## Step 5: Configure Your Application

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` and add your Google OAuth credentials:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   SESSION_SECRET_KEY=your-random-secret-key-here
   ```

3. Generate a secure session secret key:
   ```python
   import secrets
   print(secrets.token_urlsafe(32))
   ```
   Or use an online generator: https://randomkeygen.com/

## Step 6: Install Dependencies

Make sure you have all required packages installed:

```bash
pip install -r requirements.txt
```

This will install `authlib` and other required dependencies.

## Step 7: Test the Integration

1. Start your FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Navigate to `http://127.0.0.1:8000/login`
3. Click on **"Sign up with Google"**
4. You should be redirected to Google's login page
5. After logging in, you'll be redirected back to the application

## Troubleshooting

### Error: "redirect_uri_mismatch"
- Make sure the redirect URI in Google Cloud Console exactly matches: `http://127.0.0.1:8000/auth/google/callback`
- Check for trailing slashes or protocol mismatches (http vs https)

### Error: "invalid_client"
- Verify your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` are correct
- Make sure there are no extra spaces or quotes around the values

### Error: "access_denied"
- Check that you've added test users in the OAuth consent screen (for development)
- Make sure the OAuth consent screen is published (for production)

### User not being created
- Check your database connection
- Verify the `google_id` column exists in the `register` table
- Check server logs for error messages

## Production Deployment

When deploying to production:

1. Update the **Authorized JavaScript origins** and **Authorized redirect URIs** in Google Cloud Console to use your production domain
2. Make sure your `.env` file uses production credentials
3. Use HTTPS (Google OAuth requires HTTPS in production)
4. Set a strong `SESSION_SECRET_KEY`
5. Consider publishing your OAuth consent screen (after review) for public use

## Security Notes

- Never commit your `.env` file to version control
- Keep your `GOOGLE_CLIENT_SECRET` secure
- Use strong, randomly generated `SESSION_SECRET_KEY`
- Regularly rotate your OAuth credentials
- Monitor OAuth usage in Google Cloud Console

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Authlib Documentation](https://docs.authlib.org/)
- [FastAPI OAuth Tutorial](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/)
