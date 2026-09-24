import streamlit as st
import zipfile
import io
import os
import time
from pypdf import PdfReader
from google import genai
from supabase import create_client, Client
from datetime import datetime

# ---------------------------------------------------------
# Seiten-Konfiguration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Industriemeister Metall - Lern & Praxis-App", 
    page_icon="🛠️", 
    layout="wide"
)

# Supabase-Verbindung herstellen
@st.cache_resource
def init_supabase() -> Client:
    # Greift auf die Schlüsselnamen in der secrets.toml zu
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"⚠️ Datenbankverbindung fehlgeschlagen: {e}")
    st.stop()

# Ordner für dauerhafte Wissensbasis auf der Festplatte anlegen
SPEICHER_ORDNER = "wissensspeicher"
os.makedirs(SPEICHER_ORDNER, exist_ok=True)

# Automatisch bereits gespeicherte Skripte von der Festplatte in die Session laden
if "wissensbasis" not in st.session_state:
    st.session_state.wissensbasis = {}
    for datei in os.listdir(SPEICHER_ORDNER):
        if datei.endswith(".txt"):
            dateipfad = os.path.join(SPEICHER_ORDNER, datei)
            with open(dateipfad, "r", encoding="utf-8") as f:
                # Entfernt die Endung .txt für die Anzeige in der App
                original_name = datei[:-4]
                st.session_state.wissensbasis[original_name] = f.read()

# ---------------------------------------------------------
# Session State für Benutzer-Session initialisieren
# ---------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "user_points" not in st.session_state:
    st.session_state.user_points = 0
if "lernmodus" not in st.session_state:
    st.session_state.lernmodus = "👤 Solo-Lernen (Für mich üben)"

# ---------------------------------------------------------
# Cloud-Login & Registrierung (Supabase)
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.title("🛡️ Industriemeister Metall – Prüfungstrainer")
    st.markdown("### Willkommen! Bitte melde dich an, um zu starten.")
    
    col_login, _ = st.columns([2, 1])
    with col_login:
        tab_login, tab_register = st.tabs(["🔑 Anmelden", "📝 Neues Konto"])
        
        # TAB 1: LOGIN
        with tab_login:
            user_input = st.text_input("Benutzername / Kürzel:", key="login_user")
            pw_input = st.text_input("Passwort:", type="password", key="login_pw")
            
            st.markdown("---")
            modus_wahl = st.radio(
                "Wähle deinen Modus:",
                ["👤 Solo-Lernen (Für mich üben)", "🏆 Challenge-Modus (Multiplayer & Leaderboard)"],
                help="Im Challenge-Modus fließen deine Punkte in das Gruppen-Ranking ein!"
            )
            
            if st.button("🚀 Jetzt Starten", type="primary"):
                if user_input.strip() and pw_input:
                    # In Supabase prüfen
                    res = supabase.table("users").select("*").eq("username", user_input.strip()).eq("password", pw_input).execute()
                    
                    if res.data:
                        user_data = res.data[0]
                        st.session_state.logged_in = True
                        st.session_state.username = user_data["username"]
                        st.session_state.user_points = user_data.get("points", 0)
                        st.session_state.lernmodus = modus_wahl
                        
                        # Online-Status aktualisieren
                        supabase.table("users").update({"last_active": datetime.now().isoformat()}).eq("username", st.session_state.username).execute()
                        
                        st.success(f"Willkommen zurück, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Ungültiger Benutzername oder falsches Passwort.")
                else:
                    st.warning("Bitte gib Benutzername und Passwort ein.")

        # TAB 2: REGISTRIERUNG
        with tab_register:
            reg_user = st.text_input("Wunsch-Benutzername:", key="reg_user")
            reg_pw = st.text_input("Passwort festlegen:", type="password", key="reg_pw")
            
            if st.button("Konto anlegen & Einloggen"):
                if reg_user.strip() and reg_pw:
                    # Prüfen, ob Benutzer bereits existiert
                    existing = supabase.table("users").select("username").eq("username", reg_user.strip()).execute()
                    if existing.data:
                        st.error("Dieser Benutzername ist leider schon vergeben!")
                    else:
                        # Neuen User anlegen
                        new_user = {
                            "username": reg_user.strip(),
                            "password": reg_pw,
                            "points": 0,
                            "last_active": datetime.now().isoformat()
                        }
                        supabase.table("users").insert(new_user).execute()
                        
                        st.session_state.logged_in = True
                        st.session_state.username = reg_user.strip()
                        st.session_state.user_points = 0
                        st.session_state.lernmodus = "👤 Solo-Lernen (Für mich üben)"
                        
                        st.success(f"Konto erfolgreich erstellt! Willkommen, {reg_user}!")
                        st.rerun()
                else:
                    st.warning("Bitte wähle einen Benutzernamen und ein Passwort.")

    st.stop()

# ---------------------------------------------------------
# Sidebar: User-Status & Navigation
# ---------------------------------------------------------
st.sidebar.title("🛠️ Meister-Trainer")

# Profil-Box oben in der Sidebar
st.sidebar.info(f"👤 **{st.session_state.username}**\n\n📌 *{st.session_state.lernmodus}*")
if st.sidebar.button("🚪 Abmelden"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

st.sidebar.markdown("---")

# Fachbereich-Auswahl (BQ & HQ)
bereich_kategorie = st.sidebar.selectbox(
    "1. Themenbereich wählen:",
    ["Basisqualifikation (BQ)", "Hauptqualifikation (HQ)"]
)

if bereich_kategorie == "Basisqualifikation (BQ)":
    fach = st.sidebar.selectbox(
        "2. Fach wählen:",
        [
            "Betriebswirtschaftliches Handeln (BWH)",
            "Naturwissenschaftliche & technische Grundlagen (NTG)",
            "Rechtsbewusstes Handeln (RBH)",
            "Methoden der Information, Kommunikation & Planung (MIK)",
            "Zusammenarbeit im Betrieb (ZIK / AEVO)"
        ]
    )
else:
    fach = st.sidebar.selectbox(
        "2. Fach wählen:",
        [
            "Betriebstechnik",
            "Fertigungstechnik",
            "Montagetechnik",
            "Betriebliches Kostenwesen"
        ]
    )

st.sidebar.markdown("---")

# Funktion / Modul auswählen
modul = st.sidebar.radio(
    "3. Modul wählen:",
    [
        "🏆 Challenge & Leaderboard",  # <-- NEU!
        "🤖 KI-Prüfungstrainer", 
        "⚙️ Praxis-Rechner & Tools", 
        "📚 Formelsammlung & Zusammenfassungen",
        "📁 Skripte & ZIP-Wissensbasis"
    ]
)

st.sidebar.markdown("---")
api_key = st.sidebar.text_input("🔑 Gemini API Key:", type="password")
st.sidebar.caption("Sicherer Schlüssel zur Generierung der Aufgaben")

st.sidebar.markdown("---")
st.sidebar.caption("Prüfungsvorbereitung Industriemeister Metall")

# ---------------------------------------------------------
# Modul: Challenge & Leaderboard
# ---------------------------------------------------------
if modul == "🏆 Challenge & Leaderboard":
    st.title("🏆 Challenge & Leaderboard")
    st.caption("Tritt gegen deine Meisterschul-Kollegen an und sichere dir Platz 1!")

    tab_rank, tab_duell, tab_admin = st.tabs(["📊 Bestenliste", "⚔️ Duelle / Herausforderungen", "📦 Fragen-Tresor"])

    # TAB 1: LEADERBOARD
    with tab_rank:
        st.subheader("🥇 Ranking der Meisterschüler")
        try:
            # Alle User geordnet nach Punkten abrufen
            users_res = supabase.table("users").select("username, points, last_active").order("points", desc=True).execute()
            if users_res.data:
                for idx, u in enumerate(users_res.data, start=1):
                    # Online-Status prüfen (aktiv innerhalb der letzten 10 Min)
                    # Medaillen für die Top 3
                    krone = "🥇 " if idx == 1 else "🥈 " if idx == 2 else "🥉 " if idx == 3 else f"#{idx} "
                    
                    c1, c2, c3 = st.columns([3, 2, 2])
                    with c1:
                        st.markdown(f"**{krone}{u['username']}**")
                    with c2:
                        st.markdown(f"⭐ **{u.get('points', 0)} Punkte**")
                    with c3:
                        st.caption("🟢 Aktiv" if u['username'] == st.session_state.username else "⚪ Registriert")
                    st.divider()
            else:
                st.info("Noch keine Teilnehmer in der Bestenliste.")
        except Exception as e:
            st.error(f"Fehler beim Laden der Bestenliste: {e}")

    # TAB 2: DUELLE
    with tab_duell:
        st.subheader("⚔️ Jemanden herausfordern")
        
        # Liste aller anderen User holen
        all_users = supabase.table("users").select("username").neq("username", st.session_state.username).execute()
        gegner_liste = [u["username"] for u in all_users.data] if all_users.data else []

        if gegner_liste:
            col_gegner, col_fach = st.columns(2)
            with col_gegner:
                gegener_wahl = st.selectbox("Wähle einen Gegner:", gegner_liste)
            with col_fach:
                duell_fach = st.selectbox("Fach für das Duell:", ["BWH", "NTG", "RBH", "Fertigungstechnik"])

            if st.button("🔥 Herausforderung senden", type="primary"):
                neues_duell = {
                    "challenger": st.session_state.username,
                    "opponent": gegener_wahl,
                    "fach": duell_fach,
                    "status": "pending",
                    "challenger_score": 0,
                    "opponent_score": 0
                }
                supabase.table("duelle").insert(neues_duell).execute()
                st.success(f"Herausforderung an **{gegener_wahl}** in **{duell_fach}** wurde gesendet!")
                st.rerun()
        else:
            st.info("Es sind noch keine anderen Kollegen registriert. Schicke deinen Kollegen den Link, damit sie ein Konto anlegen!")

        st.markdown("---")
        st.subheader("📬 Meine aktuellen Duelle")
        
        # Eigene Duelle abrufen
        my_duels = supabase.table("duelle").select("*").or_(f"challenger.eq.{st.session_state.username},opponent.eq.{st.session_state.username}").execute()
        if my_duels.data:
            for d in my_duels.data:
                vs_text = f"⚔️ **{d['challenger']}** vs. **{d['opponent']}** ({d['fach']})"
                st.write(vs_text)
                st.caption(f"Status: {d['status']} | Punkte: {d['challenger_score']} : {d['opponent_score']}")
                st.divider()
        else:
            st.caption("Keine aktiven Duelle vorhanden.")

    # TAB 3: FRAGEN-TRESOR (Anti-503 KI-Cache)
    with tab_admin:
        st.subheader("📦 Fragen-Tresor vorbefüllen")
        st.caption("Generiere vorab Fragen für den Tresor, damit Spiele im Duell-Modus blitzschnell und ohne Gemini-Ausfälle laden.")
        
        tresor_fach = st.selectbox("Fach für Tresor-Generierung:", ["BWH", "NTG", "RBH", "Fertigungstechnik"], key="tresor_f")
        if st.button("⚡ 3 Fragen automatisch im Tresor speichern"):
            if not api_key:
                st.error("⚠️ Bitte trage zuerst deinen Gemini API Key in der Seitenleiste ein!")
            else:
                with st.spinner("KI generiert Fragen für den Tresor..."):
                    client = genai.Client(api_key=api_key)
                    prompt = f"Erstelle eine IHK-Prüfungsaufgabe für Industriemeister Metall im Fach {tresor_fach}. Gib NUR die Aufgabenstellung zurück."
                    
                    try:
                        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                        if resp.text:
                            eintrag = {
                                "fach": tresor_fach,
                                "schwierigkeit": "Prüfungsniveau",
                                "aufgaben_typ": "Textaufgabe",
                                "aufgabe": resp.text,
                                "musterloesung": "Musterlösung folgt in der Auswertung.",
                                "punkte": 10
                            }
                            supabase.table("fragen_pool").insert(eintrag).execute()
                            st.success("Frage erfolgreich im Tresor hinterlegt! 🎯")
                    except Exception as err:
                        st.error(f"Fehler bei der Generierung: {err}")

# ---------------------------------------------------------
# Modul 1: KI-Prüfungstrainer
# ---------------------------------------------------------
if modul == "🤖 KI-Prüfungstrainer":
    st.title(f"🤖 KI-Tutor: {fach}")
    st.caption("Aufgaben nach DQR6-Standard – abgestimmt auf IHK-Prüfungsanforderungen")

    col_lvl, col_mode = st.columns(2)
    with col_lvl:
        schwierigkeit = st.select_slider(
            "Schwierigkeitsgrad:",
            options=["Anfänger (Grundlagen)", "Fortgeschritten (Aufgabenstellung)", "Prüfungsniveau (IHK-Standard)"]
        )
    with col_mode:
        aufgaben_typ = st.selectbox(
            "Aufgabentyp:",
            ["Rechenaufgabe mit Lösungsweg", "Textaufgabe / Fallbeispiel", "Multiple-Choice Schnelltest", "Fachgespräch-Simulation"]
        )

    st.markdown("---")
    
    if st.button("🚀 Neue Übungsaufgabe generieren"):
        if not api_key:
            st.error("⚠️ Bitte trage zuerst deinen Gemini API-Schlüssel in der linken Leiste ein.")
        else:
            with st.spinner("KI liest deine Skripte und erstellt die Aufgabe..."):
                try:
                    # Kontext aus den hochgeladenen Dokumenten zusammenbauen
                    kontext_text = ""
                    if "wissensbasis" in st.session_state and st.session_state.wissensbasis:
                        st.info("💡 Nutze hochgeladene Skripte als Wissensbasis...")
                        for doc_name, doc_text in st.session_state.wissensbasis.items():
                            kontext_text += f"\n--- DOKUMENT: {doc_name} ---\n" + doc_text[:4000]

                    # Prompt für die KI
                    prompt = f"""
                    Du bist ein erfahrener Prüfer und Dozent für die Weiterbildung zum Industriemeister Metall (IHK).
                    Erstelle eine professionelle Übungsaufgabe für das Fach: '{fach}'.
                    
                    Anforderungen:
                    - Schwierigkeitsgrad: {schwierigkeit}
                    - Aufgabentyp: {aufgaben_typ}
                    - Orientiere dich am DQR6-Niveau (Handlungskompetenz, Meisterebene).
                    
                    Relevanter Lernstoff aus den Skripten des Teilnehmers:
                    {kontext_text if kontext_text else 'Nutze allgemeines IHK-Prüfungswissen für Industriemeister Metall.'}
                    
                    Struktur der Ausgabe:
                    1. **Aufgabenstellung** (Klar formuliert, praxisnah)
                    2. **Punktevergabe / Zeitansatz** (z. B. 10 Punkte / 12 Minuten)
                    3. **Ausführliche Musterlösung mit Lösungsweg** (Ausklappbar oder klar getrennt)
                    """

                    client = genai.Client(api_key=api_key)
                    
                    # Aktualisierte Modellliste mit aktiven Gemini 2.x Modellen
                    modelle = ['gemini-2.5-flash', 'gemini-2.0-flash']
                    response = None
                    letzter_fehler = None

                    for model_name in modelle:
                        for versuch in range(3):  # Max 3 Versuche pro Modell bei 503-Überlastung
                            try:
                                response = client.models.generate_content(
                                    model=model_name,
                                    contents=prompt,
                                )
                                if response and response.text:
                                    break
                            except Exception as err:
                                letzter_fehler = err
                                time.sleep(2)  # 2 Sekunden warten vor dem nächsten Versuch
                        if response and response.text:
                            break

                    if response and response.text:
                        st.markdown("### 📝 Generierte Aufgabe")
                        st.write(response.text)
                    else:
                        st.error(f"Server aktuell stark ausgelastet oder Modell nicht erreichbar. Details: {letzter_fehler}")

                except Exception as e:
                    st.error(f"Fehler bei der KI-Generierung: {e}")

# ---------------------------------------------------------
# Modul 2: Praxis-Rechner & Tools (Interaktiv)
# ---------------------------------------------------------
elif modul == "⚙️ Praxis-Rechner & Tools":
    st.title(f"⚙️ Interaktive Rechner – {fach}")

    if "BWH" in fach:
        tab_akkord, tab_praemie = st.tabs(["Geldakkord (Stückakkord)", "Prämienlohn"])

        with tab_akkord:
            st.subheader("Geldakkord-Berechnung")
            c1, c2, c3 = st.columns(3)
            with c1:
                grundlohn = st.number_input("Grundlohn (€/h)", value=20.0, step=0.5)
                zuschlag = st.number_input("Akkordzuschlag (%)", value=12.5, step=0.5)
            with c2:
                soll_zeit = st.number_input("Soll-Zeit pro Stück (Min.)", value=12.0, step=0.5)
                arbeitszeit = st.number_input("Arbeitszeit (h/Woche)", value=40.0, step=1.0)
            with c3:
                ist_menge = st.number_input("Ist-Leistung (Stück/h)", value=6.0, step=0.5)

            # Formeln (AKLPL Logik)
            ars = grundlohn * (1 + (zuschlag / 100))
            normalleistung = 60 / soll_zeit if soll_zeit > 0 else 0
            stueckgeldsatz = ars / normalleistung if normalleistung > 0 else 0
            zeitgrad = (ist_menge / normalleistung) * 100 if normalleistung > 0 else 0
            effektiver_lohn = ars * (zeitgrad / 100)

            st.markdown("---")
            res1, res2, res3 = st.columns(3)
            res1.metric("Akkordrichtsatz (ARS)", f"{ars:.2f} €/h")
            res2.metric("Stückgeldsatz", f"{stueckgeldsatz:.2f} €/Stück")
            res3.metric("Effektiver Lohn", f"{effektiver_lohn:.2f} €/h", delta=f"{zeitgrad:.1f}% Zeitgrad")

        with tab_praemie:
            st.subheader("Prämienlohn-Berechnung")
            p_grund = st.number_input("Grundlohn (€/h)", value=17.20, step=0.5)
            p_praemie = st.number_input("Prämie (€/h)", value=4.80, step=0.1)
            st.metric("Gesamtlohn", f"{p_grund + p_praemie:.2f} €/h")

    elif "NTG" in fach:
        st.subheader("NTG-Formelrechner")
        st.info("Rechner für Mechanik (Kräfte, Drehmoment), Elektrotechnik (Ohm'sches Gesetz) und Wärmelehre in Vorbereitung.")

    else:
        st.info(f"Für das Fach **{fach}** steht in Kürze ein spezifisches Rechentool zur Verfügung.")

# ---------------------------------------------------------
# Modul 3: Formelsammlung
# ---------------------------------------------------------
elif modul == "📚 Formelsammlung & Zusammenfassungen":
    st.title(f"📚 Formelsammlung: {fach}")
    st.write("Wichtige Formeln, Definitionen und rechtliche Grundlagen auf einen Blick.")

# ---------------------------------------------------------
# Modul 4: Skripte & ZIP-Wissensbasis
# ---------------------------------------------------------
elif modul == "📁 Skripte & ZIP-Wissensbasis":
    st.title("📁 Unterlagen & Wissensspeicher")
    st.caption("Lade deine ZIP-Archive oder PDF-Skripte hoch. Sie bleiben dauerhaft auf deiner Festplatte gespeichert!")

    uploaded_files = st.file_uploader(
        "ZIP-Dateien oder PDFs hochladen:", 
        accept_multiple_files=True, 
        type=["zip", "pdf"]
    )
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            filename = uploaded_file.name

            # FALL 1: Einzelne PDF-Datei
            if filename.endswith(".pdf"):
                pdf_reader = PdfReader(uploaded_file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() or ""
                
                # In Session State und auf Festplatte speichern
                st.session_state.wissensbasis[filename] = text
                speicher_pfad = os.path.join(SPEICHER_ORDNER, f"{filename}.txt")
                with open(speicher_pfad, "w", encoding="utf-8") as f:
                    f.write(text)
                st.success(f"📄 PDF dauerhaft gespeichert: **{filename}**")

            # FALL 2: ZIP-Archiv
            elif filename.endswith(".zip"):
                with zipfile.ZipFile(uploaded_file, "r") as z:
                    pdf_count = 0
                    for zip_info in z.infolist():
                        if zip_info.filename.endswith(".pdf") and not zip_info.filename.startswith("__MACOSX"):
                            with z.open(zip_info) as pdf_file:
                                pdf_bytes = io.BytesIO(pdf_file.read())
                                pdf_reader = PdfReader(pdf_bytes)
                                text = ""
                                for page in pdf_reader.pages:
                                    text += page.extract_text() or ""
                                
                                sauberer_name = os.path.basename(zip_info.filename)
                                if sauberer_name:
                                    st.session_state.wissensbasis[sauberer_name] = text
                                    speicher_pfad = os.path.join(SPEICHER_ORDNER, f"{sauberer_name}.txt")
                                    with open(speicher_pfad, "w", encoding="utf-8") as f:
                                        f.write(text)
                                    pdf_count += 1
                    st.success(f"📦 ZIP entpackt: **{pdf_count} PDF-Dokumente** dauerhaft auf Festplatte gesichert!")

    # Vorschau & Verwaltung der geladenen Dokumente
    st.markdown("---")
    st.subheader(f"📚 Gespeicherte Skripte ({len(st.session_state.wissensbasis)} Dokumente vorhanden)")
    
    if st.session_state.wissensbasis:
        geladene_dateien = list(st.session_state.wissensbasis.keys())
        
        col_auswahl, col_del = st.columns([3, 1])
        with col_auswahl:
            auswahl_doc = st.selectbox("Dokument für Vorschau wählen:", geladene_dateien)
        with col_del:
            st.write(" ")
            st.write(" ")
            if st.button("🗑️ Dokument löschen"):
                del st.session_state.wissensbasis[auswahl_doc]
                pfad_zum_loeschen = os.path.join(SPEICHER_ORDNER, f"{auswahl_doc}.txt")
                if os.path.exists(pfad_zum_loeschen):
                    os.remove(pfad_zum_loeschen)
                st.success(f"'{auswahl_doc}' wurde gelöscht.")
                st.rerun()

        if auswahl_doc and auswahl_doc in st.session_state.wissensbasis:
            st.info(f"Anzahl Zeichen: **{len(st.session_state.wissensbasis[auswahl_doc])}**")
            with st.expander("📄 Textauszug anzeigen"):
                st.write(st.session_state.wissensbasis[auswahl_doc][:2000] + "\n\n... [Vorschau gekürzt]")
    else:
        st.info("Noch keine Skripte dauerhaft gespeichert. Lade oben deine Unterlagen hoch.")