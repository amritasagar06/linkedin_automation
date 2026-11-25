from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlparse

import streamlit as st

from cloud_common import db, read_private_value, setting
from linkedin_api import create_post, finish_authorization, make_authorization_url


def valid_substack_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "substack.com" or host.endswith(".substack.com"))


def login_gate() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.title("Daily Interview Post Review")
    st.write("Sign in to review your private drafts and approve LinkedIn publication.")
    password = setting("APP_PASSWORD")
    if not password:
        st.error("APP_PASSWORD is not set in Streamlit Cloud secrets.")
        return False
    with st.form("login"):
        entered = st.text_input("App password", type="password")
        submit = st.form_submit_button("Sign in")
    if submit:
        if hmac.compare_digest(entered, password):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("That password did not match.")
    return False


st.set_page_config(page_title="Daily Interview Post Review", layout="wide")
if not login_gate():
    st.stop()

client = db()
st.title("Daily Interview Post Review")
st.caption("The daily cloud job selects a question and creates drafts. LinkedIn publishes only after you approve the exact post below.")

# LinkedIn OAuth callback returns to the same HTTPS app URL with code and state.
callback_code = st.query_params.get("code")
callback_state = st.query_params.get("state")
if callback_code and callback_state:
    try:
        finish_authorization(str(callback_code), str(callback_state))
        st.query_params.clear()
        st.success("LinkedIn connected. The access token is encrypted in the app database.")
        st.rerun()
    except Exception as exc:
        st.error(f"LinkedIn connection failed: {exc}")

person_urn = read_private_value("linkedin_person_urn")
col1, col2 = st.columns([2, 1])
with col1:
    if person_urn:
        st.success(f"LinkedIn connected: {person_urn}")
    else:
        st.warning("LinkedIn is not connected yet. Connect it before the first approval.")
with col2:
    try:
        connect_url = make_authorization_url()
        st.link_button("Connect / reconnect LinkedIn", connect_url, use_container_width=True)
    except Exception as exc:
        st.error(str(exc))

rows = client.table("posts").select("*").order("scheduled_date", desc=True).limit(30).execute().data
if not rows:
    st.info("No daily drafts yet. The scheduled GitHub Actions job will create one at 2:00 PM Singapore time.")
    selected = None
else:
    choices = {f"{r['scheduled_date']} · {r['status']} · {r['title']}": r for r in rows}
    requested_id = st.query_params.get("draft")
    default_label = next((label for label, row in choices.items() if requested_id and row["id"] == requested_id), next(iter(choices)))
    selected = choices[st.selectbox("Daily drafts", list(choices), index=list(choices).index(default_label))]

if selected:
    st.divider()
    st.subheader(selected["title"])
    st.caption(f"Question: {selected['question']} · Status: **{selected['status']}**")
    st.markdown("#### Substack article draft")
    st.markdown(selected["article"])
    st.markdown("#### LinkedIn post draft")

    if selected["status"] in ("published", "publishing", "publication_unknown"):
        st.text_area("Published / queued text", value=selected["linkedin_text"], height=180, disabled=True)
        if selected["status"] == "published":
            st.success(f"Published on LinkedIn. Post reference: {selected['linkedin_post_urn'] or 'created'}")
        elif selected["status"] == "publication_unknown":
            st.error("The request ended without a reliable response. Check LinkedIn manually before retrying so you do not publish twice.")
        else:
            st.warning("A LinkedIn publish request is in progress. Do not submit it again.")
    else:
        with st.form(f"edit_{selected['id']}"):
            edited_article = st.text_area("Article (Markdown)", value=selected["article"], height=360)
            substack_url = st.text_input("Published Substack URL", value=selected["substack_url"])
            starting_linkedin = selected["linkedin_text"].replace("[SUBSTACK_URL]", substack_url.strip()) if substack_url.strip() else selected["linkedin_text"]
            edited_linkedin = st.text_area("LinkedIn post", value=starting_linkedin, height=190)
            save = st.form_submit_button("Save reviewed content")
        if save:
            resolved_text = edited_linkedin.replace("[SUBSTACK_URL]", substack_url.strip()) if substack_url.strip() else edited_linkedin
            if substack_url.strip() and not valid_substack_url(substack_url):
                st.error("Use the public HTTPS URL from your Substack publication.")
            else:
                new_status = "ready_for_approval" if valid_substack_url(substack_url) else "pending_substack"
                client.table("posts").update({
                    "article": edited_article,
                    "linkedin_text": resolved_text,
                    "substack_url": substack_url.strip(),
                    "status": new_status,
                    "approval_hash": "",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", selected["id"]).execute()
                st.success("Saved. Review the text again before approving.")
                st.rerun()

        st.info("First publish the article manually on Substack. Paste its public URL above and save. Then check the final LinkedIn copy and approve it below.")
        st.text_area("Final LinkedIn text for approval", value=selected["linkedin_text"], height=150, disabled=True)
        can_publish = valid_substack_url(selected["substack_url"]) and person_urn and selected["status"] == "ready_for_approval"
        approved = st.checkbox("I have reviewed this exact post and approve publishing it publicly to LinkedIn.", key=f"approve_{selected['id']}")
        if st.button("Approve and publish to LinkedIn", disabled=not (approved and can_publish), type="primary"):
            current = client.table("posts").select("*").eq("id", selected["id"]).single().execute().data
            digest = hashlib.sha256((current["linkedin_text"] + "\n" + current["substack_url"]).encode("utf-8")).hexdigest()
            client.table("posts").update({"status": "publishing", "approval_hash": digest,
                                           "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", selected["id"]).execute()
            try:
                post_urn = create_post(current["linkedin_text"])
                client.table("posts").update({"status": "published", "linkedin_post_urn": post_urn,
                                               "error_message": "", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", selected["id"]).execute()
                st.success("Published to LinkedIn.")
                st.rerun()
            except Exception as exc:
                # A timeout may occur after LinkedIn accepted the post; never retry automatically.
                client.table("posts").update({"status": "publication_unknown", "error_message": str(exc)[:1000],
                                               "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", selected["id"]).execute()
                st.error(f"LinkedIn did not return a clear result. Check your LinkedIn profile before retrying: {exc}")

st.divider()
with st.expander("Question selection: automatic by default"):
    questions = client.table("questions").select("id,sequence_no,topic,question").order("sequence_no").execute().data
    if questions:
        st.write("Each day the job advances to the next question. You can set a one-time override for the next draft:")
        labels = {f"{q['sequence_no']}. {q['question']}": str(q["id"]) for q in questions}
        current_override = client.table("app_settings").select("value").eq("name", "next_question_id").limit(1).execute().data
        current_id = current_override[0]["value"] if current_override else ""
        current_label = next((label for label, qid in labels.items() if qid == current_id), next(iter(labels)))
        chosen = st.selectbox("Use this question for the next daily draft", list(labels), index=list(labels).index(current_label))
        q1, q2 = st.columns(2)
        if q1.button("Set one-time question override"):
            client.table("app_settings").upsert({"name": "next_question_id", "value": labels[chosen]}).execute()
            st.success("Saved. The next daily run will use this question once.")
        if q2.button("Clear override and continue automatic rotation"):
            client.table("app_settings").upsert({"name": "next_question_id", "value": ""}).execute()
            st.success("Automatic rotation restored.")

with st.expander("Writing style examples"):
    st.write("Add your own past posts here. The generator uses up to 10 examples to match voice and structure. LinkedIn's API does not normally grant apps permission to read personal post history.")
    with st.form("style_example_form", clear_on_submit=True):
        example = st.text_area("Paste one of your past LinkedIn posts")
        add_example = st.form_submit_button("Save style example")
    if add_example and example.strip():
        client.table("style_examples").insert({"body": example.strip()}).execute()
        st.success("Style sample saved.")
    samples = client.table("style_examples").select("id,body,created_at").order("created_at", desc=True).limit(10).execute().data
    for sample in samples:
        with st.container(border=True):
            st.caption(sample["created_at"])
            st.write(sample["body"][:1200])
            if st.button("Delete sample", key=f"delete_{sample['id']}"):
                client.table("style_examples").delete().eq("id", sample["id"]).execute()
                st.rerun()
