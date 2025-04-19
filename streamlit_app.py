###############################
# Investment Research Screener (single‑file)                        
# — New‑chat UX now matches ChatGPT: first message auto‑creates conv
###############################

import os, json, urllib.parse, requests
from typing import List, Dict, Any, Optional
from datetime import datetime

import streamlit as st
from supabase import create_client, Client

# ---------- CONFIG --------------------------------------------------
SUPABASE_URL: str = st.secrets["supabase"]["url"]
SUPABASE_KEY: str = st.secrets["supabase"]["key"]
API_URL: Optional[str] = st.secrets.get("API_URL") or os.getenv("API_URL")

# ---------- INITIALISERS -------------------------------------------
@st.cache_resource(show_spinner=False)
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()


def init_session_state() -> None:
    defaults = {
        "logged_in": False,
        "user_email": "",
        "user_id": None,
        "conversation_id": None,
        "conversation_history": [],
        "messages": [],
        "pick_conv": None,  # sidebar selectbox state
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

# ---------- CHAT CONTEXT / HELPERS ---------------------------------

def build_context(max_turns: int = 3) -> str:
    """Return a compact conversation snippet of the last *max_turns* pairs.
    Format:USER: ....\nASSISTANT: ....
        ---
    This string can be sent to the LLM / API so it preserves minimal context
    without hitting token limits.
    """
    msgs = st.session_state.messages[-2 * max_turns :]
    lines = []
    for m in msgs:
        role = "USER" if m["role"] == "user" else "ASSISTANT"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)

# ---------- HELPERS -------------------------------------------------

def query_url(query: str) -> str:
    encoded = urllib.parse.quote_plus(query)
    return (
        "https://www.screener.in/screen/raw/?sort=&order=&source_id=&query="
        + encoded
        + "&page=1"
    )


def fetch_research(query: str,context: str) -> Dict[str, Any]:
    
    if not API_URL:
        raise RuntimeError("API_URL missing – add to secrets or env var")
    if context:
        # Two line‑breaks keep the user input visually separate
        combined_query = f"{context}\n\n{query}"
    else:
        combined_query = query

    payload = {"query": combined_query}
    resp = requests.post(API_URL, json=payload)
    resp.raise_for_status()
    return resp.json()

# ---------- DATABASE UTILS -----------------------------------------

def get_or_create_user(email: str, auth_id: str) -> int:
    resp = supabase.table("users").select("id").eq("auth_id", auth_id).eq("status", "active").execute()
    if resp.data:
        return resp.data[0]["id"]
    ins = supabase.table("users").insert({"auth_id": auth_id, "email": email,"status": "active"}).execute()
    return ins.data[0]["id"]


def list_conversations(user_id: int) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    resp = (
        supabase.table("user_conversations")
        .select("id, title, created_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


def create_conversation(user_id: int, title) -> Dict[str, Any]:
    ins = (
        supabase.table("user_conversations")
        .insert({"user_id": user_id, "title": title, "status": "active"}).execute()
    )
    return {
        "id": ins.data[0]["id"],
        "title": title or "",
        "created_at": ins.data[0]["created_at"],
    }


def save_message(conv_id: int, role: str, content: str) -> None:
    supabase.table("messages").insert({
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "status": "active",
    }).execute()


def load_messages(conv_id: int) -> List[Dict[str, str]]:
    resp = (
        supabase.table("messages")
        .select("role, content, created_at")
        .eq("conversation_id", conv_id)
        .eq("status", "active")
        .order("created_at")
        .execute()
    )
    return [{"role": m["role"], "content": m["content"]} for m in resp.data]

# ---------- AUTH ----------------------------------------------------

def sign_in(email: str, password: str) -> bool:
    auth_resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
    if not auth_resp:
        return False
    user = auth_resp.user
    st.session_state.logged_in = True
    st.session_state.user_email = user.email
    st.session_state.user_id = get_or_create_user(user.email, user.id)
    return True


def sign_up(email: str, password: str) -> bool:
    auth_resp = supabase.auth.sign_up({"email": email, "password": password})
    if not auth_resp:
        return False
    user = auth_resp.user
    st.session_state.logged_in = True
    st.session_state.user_email = user.email
    st.session_state.user_id = get_or_create_user(user.email, user.id)
    return True


def sign_out():
    supabase.auth.sign_out()
    for k in ["logged_in", "user_email", "user_id", "conversation_id", "messages", "pick_conv"]:
        st.session_state[k] = False if isinstance(st.session_state[k], bool) else None

# ---------- UI COMPONENTS ------------------------------------------

def sidebar_auth() -> None:
    with st.sidebar:
        st.markdown(
            "<h1 style='margin-top:0'>🤖 Screener Chat</h1><span style='font-weight:200'>filter stocks on Screener.in with English</span>",
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown("## 🔐 Authentication")
        if st.session_state.logged_in:
            st.success(f"👤 {st.session_state.user_email}")
            if st.button("Log Out"):
                sign_out(); st.rerun()
        else:
            tab = st.radio("Account", ["Sign In", "Sign Up"], horizontal=True)
            email = st.text_input("Email", key="auth_email")
            pwd = st.text_input("Password", type="password", key="auth_pwd")
            if st.button("Submit"):
                ok = sign_in(email, pwd) if tab == "Sign In" else sign_up(email, pwd)
                if ok:
                    st.rerun()
                else:
                    st.error("Auth failed – check credentials / confirmation e‑mail.")

def sidebar_history() -> None:
    if not st.session_state.logged_in:
        return
    convs = list_conversations(st.session_state.user_id)
    # map ID → full row for later lookup
    conv_by_id = {c["id"]: c for c in convs}
    # build options list of IDs (+ None) so identity stays stable
    options = [None] + [c["id"] for c in convs]
    # before building the selectbox
    if ( "pick_conv" not in st.session_state or st.session_state.pick_conv != st.session_state.conversation_id ):
        st.session_state.pick_conv = st.session_state.conversation_id
    default_id = st.session_state.conversation_id
    def handle_conv_change():
        sel = st.session_state.pick_conv  # current selectbox value
        if sel is None:                              # “➕ New conversation”
            st.session_state.conversation_id = None
            st.session_state.messages = []
        else:
            st.session_state.conversation_id = sel
            st.session_state.messages = load_messages(sel)
        # st.rerun()  # refresh UI immediately

    with st.sidebar:
        st.divider(); st.header("Chat History")
        st.caption("Select a conversation or start a new one ⤵️")
        pick = st.selectbox(
            "Select conversation",
            options,
            # index=options.index(default_id) if default_id in options else 0,
            key="pick_conv",
            format_func=lambda cid: "➕ New conversation"
            if cid is None
            else f"{conv_by_id[cid]['title'] or cid} "
                 f"({conv_by_id[cid]['created_at'][:19]})",
            on_change=handle_conv_change, 
        )
        # ➕ New conversation chosen – leave conv_id None until first msg
        # if pick is None:
        #         st.session_state.conversation_id = None
        #         st.session_state.messages = []
        # # Existing conversation selected
        # else:
        #     if pick != st.session_state.conversation_id:
        #         st.session_state.conversation_id = pick
        #         st.session_state.messages = load_messages(pick)
        #         print(f"st.session_state.messages {pick} {st.session_state.messages}")
        #         print(f"pick {pick}")
        #         print(f"st.session_state.conversation_id {st.session_state.conversation_id}")
                # st.rerun()

# ---------- CHAT MAIN TAB ------------------------------------------

def ensure_conv_for_first_msg() -> None:
    """Create a new conversation on‑the‑fly if none exists when first message sent."""
    if st.session_state.conversation_id is None:
        new_conv = create_conversation(st.session_state.user_id," ")
        st.session_state.conversation_id = new_conv["id"]
        # push into history & pre‑select in sidebar
        st.session_state.conversation_history.insert(0, new_conv)



def chat_tab() -> None:
    # st.header("Investment Research Chat")
    # messages_box = st.container(height=600, border=True)
    print("st.session_state.pick_conv:", st.session_state.pick_conv)
    print("conv id:", st.session_state.conversation_id)
    # with messages_box:
    #     if not st.session_state.messages:
    #         st.markdown(
    #             "<div style='color:#888;text-align:center;padding-top:6rem;'>"
    #             "Start typing below to begin a conversation…"
    #             "</div>",
    #             unsafe_allow_html=True,
    #         )
    #     else:
    #         for m in st.session_state.messages:
    #             with st.chat_message(m["role"]):
    #                 st.markdown(m["content"])

    # user_msg = st.chat_input("Your Screener Query")
    
    # ensure_conv_for_first_msg()
    # cid = st.session_state.conversation_id

    # st.session_state.messages.append({"role": "user", "content": user_msg})
    # save_message(cid, "user", user_msg)
    
    # with messages_box:
    #     # ----- placeholder assistant bubble -----
    #     placeholder = st.chat_message("assistant")
    #     placeholder.markdown("_Researching…_")
    # 1️⃣ Read user input first
    placeholder_bool = False
    user_msg = st.chat_input("Your Screener Query")
    if user_msg:
        ensure_conv_for_first_msg()
        cid = st.session_state.conversation_id
        st.session_state.messages.append({"role": "user", "content": user_msg})
        save_message(cid, "user", user_msg)

    # 2️⃣ Now render the chat box
    messages_box = st.container(height=600, border=True)
    with messages_box:
        if st.session_state.messages or placeholder_bool:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])
        else:
            st.markdown(
                "<div style='color:#888;text-align:center;padding-top:6rem;'>"
                "Start typing below to begin a conversation…"
                "</div>",
                unsafe_allow_html=True,
            )
    context_snippet = build_context(max_turns=3)
    QUERY_PREFIX = "get query for this\n\n"

    if user_msg and user_msg.strip():
        api_prompt = QUERY_PREFIX + user_msg
        with messages_box:
            placeholder_bool = True
            placeholder = st.chat_message("assistant")
            placeholder.markdown("_Researching…_")

        with st.spinner("Researching…"):
            try:
                result = fetch_research(api_prompt,context_snippet)
                # result = json.loads("""
                #     {"success":true,"message":"Investment research pipeline completed successfully.","error_message":null,"data":{"analysis":{"thought":"The user is focused on identifying financially robust companies that have consistently demonstrated strong growth in both revenue and profits, along with solid return on equity and attractive earnings yield, indicating a preference for sustainable growth and value.","objectives":["Identify companies with consistent revenue and profit growth over 10% annually.","Seek companies with a return on equity above 15%.","Find investments with an earnings yield greater than 7%."]},"query":"(Sales growth 10Years > 10) AND (Profit growth 10Years > 10) AND (Return on equity > 15) AND (Earnings yield > 7)"}}
                #     """)
            except Exception as err:
                print(err)
                err_msg = f"⚠️ **Error**: Could not process your request. Please try again."   
                placeholder.markdown(err_msg)
                save_message(cid, "assistant", err_msg)
                return
        print("Result:",result)

        # guard against malformed payloads
        if not isinstance(result, dict):
            print("Malformed result:", result)
            msg = "⚠️ **Error**: Could not process your request. Please try again."
            placeholder.markdown(msg)
            save_message(cid, "assistant", msg)
            return

        if not result.get("success", True):
            print("Malformed result:", result)
            msg = f"⚠️ **Error**: Could not process your request. Please try again."
            placeholder.markdown(msg)
            save_message(cid, "assistant", msg)
            return
        
        # if result.get("message"): st.info(result["message"])
        data = result.get("data", {})
        analysis = data.get("analysis", {})
        generated_query = data.get("query")

        chunks = []
        if analysis.get("thought"):
            chunks.append("**💭 Thought**\n" + analysis["thought"])
        if analysis.get("objectives"):
            chunks.append("**🎯 Objectives**\n" + "\n".join("- " + o for o in analysis["objectives"]))
        if generated_query:
            chunks.append(
                "**🔍 Generated Query**\n```sql\n" + generated_query + "\n```\n[View on Screener](" + query_url(generated_query) + ")"
            )

        assistant_msg = "\n\n".join(chunks)
        # replace placeholder content
        placeholder.markdown(assistant_msg)
        st.session_state.messages.append({"role": "assistant", "content": assistant_msg})
        save_message(cid, "assistant", assistant_msg)
        st.rerun()

# ---------- APPLICATION ENTRY --------------------------------------

def main() -> None:
    st.set_page_config(page_title="Screener Chat", page_icon="🤖", layout="wide")
    
    
    sidebar_auth()
    sidebar_history()

    if not st.session_state.logged_in:
        st.title("🔐 Please sign in")
        return

    # tabs = st.tabs(["Chat", "Profile", "Settings"])
    chat_tab()
    # with tabs[0]:
        
    # with tabs[1]:
    #     st.header("Profile"); st.write("Coming soon…")
    # with tabs[2]:
    #     st.header("Settings"); st.write("Nothing to configure yet.")

if __name__ == "__main__":
    main()

# st.text(st.session_state.messages)