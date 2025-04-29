import streamlit as st
import pandas as pd
import requests
import time
import json
import io
from datetime import datetime

st.set_page_config(
    page_title="Wissenschaftliche Literaturrecherche",
    page_icon="📚",
    layout="wide"
)

# Debug-Modus für Fehlerdiagnose - auf False setzen für Produktivbetrieb
DEBUG = False

def get_publication_data(keywords, start_year, end_year, doc_types, open_access_filter, sort_by, max_results=100):
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    debug_info = st.empty()
    
    try:
        # OpenAlex API verwenden
        base_url = "https://api.openalex.org/works"
        
        # Filterbedingungen erstellen
        filters = []
        
        # Jahresfilter hinzufügen - Stelle sicher dass die Jahre als Integer sind
        if start_year and end_year:
            filters.append(f"publication_year:{int(start_year)}-{int(end_year)}")
        elif start_year:
            filters.append(f"publication_year>={int(start_year)}")
        elif end_year:
            filters.append(f"publication_year<={int(end_year)}")
        
        # Dokumenttyp-Filter hinzufügen - Korrektes Format für OR-Abfragen
        if doc_types:
            doc_type_filter = f"type:{('|'.join(doc_types))}"
            filters.append(doc_type_filter)
        
        # Open Access Filter hinzufügen
        if open_access_filter != "Alle":
            if open_access_filter == "Open Access":
                filters.append("is_oa:true")
            elif open_access_filter == "Kostenpflichtig":
                filters.append("is_oa:false")
        
        # API-Parameter vorbereiten
        params = {
            'search': keywords,
            'per_page': 100,  # Maximale Anzahl pro Seite
            'mailto': "stud7407@gmail.com"  # Korrekte Stelle für Ihre E-Mail
        }
        
        # Bei Debug-Modus auch weniger Ergebnisse holen für schnellere Tests
        if DEBUG:
            debug_info.write("DEBUG Modus: Beschränke auf 20 Ergebnisse pro Seite")
            params['per_page'] = 20
        
        # Mehrstufige Sortierung festlegen
        sort_params = []
        
        # Primäres Sortierkriterium
        if sort_by["primary"] == "Aktualität":
            sort_params.append('publication_date:desc')
        elif sort_by["primary"] == "Relevanz":
            sort_params.append('relevance_score:desc')
        elif sort_by["primary"] == "Zitationen":
            sort_params.append('cited_by_count:desc')
        
        # Sekundäres Sortierkriterium (falls vorhanden)
        if sort_by["secondary"] != "Keine":
            if sort_by["secondary"] == "Aktualität":
                sort_params.append('publication_date:desc')
            elif sort_by["secondary"] == "Relevanz":
                sort_params.append('relevance_score:desc')
            elif sort_by["secondary"] == "Zitationen":
                sort_params.append('cited_by_count:desc')
        
        # Sortierparameter zur API-Anfrage hinzufügen
        if sort_params:
            params['sort'] = ','.join(sort_params)
        
        # Filter hinzufügen
        if filters:
            params['filter'] = ','.join(filters)
        
        status_text.text("Suche läuft...")
        
        # Debug-Info anzeigen
        if DEBUG:
            debug_info.code(f"API-Aufruf: {base_url}\nParameter: {json.dumps(params, indent=2)}")
            
            # Generiere vollständige URL zur Überprüfung
            full_url = f"{base_url}?"
            for key, value in params.items():
                full_url += f"{key}={requests.utils.quote(str(value))}&"
            full_url = full_url.rstrip('&')
            debug_info.code(f"Vollständige URL: {full_url}")
        
        # API-Anfrage mit Email-Identifikation im User-Agent Header
        headers = {
            "User-Agent": "LiteraturrechercheTool/1.0 (mailto:stud7407@gmail.com)",
            "Accept": "application/json"
        }
        
        # Paginierung implementieren
        current_page = 1
        total_pages = 1  # Anfangswert, wird später aktualisiert
        collected_items = 0
        
        while current_page <= total_pages and collected_items < max_results:
            # Aktuelle Seite an die Parameter anhängen
            params['page'] = current_page
            
            # Statusaktualisierung
            status_text.text(f"Lade Seite {current_page} von geschätzt {total_pages}...")
            
            # Anfrage mit Timeout von 60 Sekunden
            try:
                response = requests.get(base_url, params=params, headers=headers, timeout=60)
                
                # Debug-Info für Response
                if DEBUG and not response.ok:
                    debug_info.error(f"API-Fehler: Status {response.status_code}")
                    debug_info.code(f"Response: {response.text}")
                
                if not response.ok:
                    # Vereinfachte Anfrage probieren (nur Basis-Parameter)
                    st.warning(f"Anfrage für Seite {current_page} fehlgeschlagen. Versuche vereinfachte Anfrage...")
                    simple_params = {
                        'search': keywords,
                        'per_page': 10,
                        'mailto': 'stud7407@gmail.com'
                    }
                    response = requests.get(base_url, params=simple_params, headers=headers, timeout=60)
                    
                    if not response.ok:
                        st.error(f"API-Fehler: Status {response.status_code}")
                        if DEBUG:
                            debug_info.code(f"Vereinfachte Anfrage fehlgeschlagen: {response.text}")
                        break  # Beende bei Fehler die Schleife und verwende die bisher gesammelten Ergebnisse
                
                # Parse JSON Antwort
                data = response.json()
                
                # Extrahiere Metadaten für Paginierung
                total_results = data.get('meta', {}).get('count', 0)
                per_page = data.get('meta', {}).get('per_page', params['per_page'])
                total_pages = (total_results + per_page - 1) // per_page  # Aufrunden
                
                # Extrahiere Ergebnisse
                items = data.get('results', [])
                
                if not items:
                    break  # Beende die Schleife, wenn keine Ergebnisse mehr zurückgegeben werden
                
                # Verarbeite die Ergebnisse
                for item in items:
                    if collected_items >= max_results:
                        break
                    
                    try:
                        # Extrahiere Jahr und konvertiere zu Integer
                        year = item.get('publication_year')
                        if not year:
                            continue
                        
                        # Immer das Jahr zu Integer konvertieren, unabhängig vom Eingabetyp
                        try:
                            # Int-Konvertierung erzwingen, um Float-Werte wie 2.015 zu 2015 zu machen
                            if year is not None:
                                # Bei Float wie 2.015 erst zu String, dann zu int konvertieren um 2015 zu erhalten
                                if isinstance(year, float):
                                    # Format 2015 statt 2 für Float 2.015
                                    year_str = str(year).replace('.', '')
                                    if ',' in year_str:
                                        year_str = year_str.replace(',', '')
                                                                # Bereinige und prüfe die Jahreszahl
                                    if len(year_str) >= 4:
                                        year = int(year_str[:4])  # Nehme die ersten 4 Ziffern
                                    else:
                                        year = int(year)  # Fallback zur direkten Konvertierung
                                else:
                                    year = int(year)
                        except (ValueError, TypeError):
                            st.warning(f"Ungültiges Jahresformat gefunden: {year}, wird übersprungen")
                            continue
                        
                        # Extrahiere Titel
                        title = item.get('title', 'Kein Titel verfügbar')
                        
                        # Extrahiere Autoren
                        authors = "Keine Autoren verfügbar"
                        author_list = item.get('authorships', [])
                        if author_list:
                            author_names = []
                            for author in author_list:
                                author_data = author.get('author', {})
                                if author_data and 'display_name' in author_data:
                                    author_names.append(author_data['display_name'])
                            if author_names:
                                authors = ", ".join(author_names)
                        
                        # Extrahiere Journal/Quelle
                        journal = "Keine Quelle verfügbar"
                        venue = item.get('primary_location', {}).get('source', {})
                        if venue and venue.get('display_name'):
                            journal = venue['display_name']
                        elif item.get('host_venue', {}).get('display_name'):
                            journal = item['host_venue']['display_name']
                        
                        # Extrahiere URL/DOI
                        url_doi = "Keine URL verfügbar"
                        if 'doi' in item and item['doi']:
                            url_doi = item['doi']
                        elif 'url' in item and item['url']:
                            url_doi = item['url']
                        
                        # Extrahiere Dokumenttyp
                        doc_type = item.get('type', 'Unbekannt')
                        
                        # Extrahiere Zitationsanzahl
                        citations = item.get('cited_by_count', 0)
                        
                        # Extrahiere Open Access Status
                        is_open_access = item.get('open_access', {}).get('is_oa', False)
                        open_access_status = "Open Access" if is_open_access else "Kostenpflichtig"
                        
                        # Füge Ergebnis hinzu
                        results.append({
                            "Titel": title,
                            "Autoren": authors,
                            "Jahr": year,
                            "Journal/Quelle": journal,
                            "Typ": doc_type,
                            "Zitationen": citations,
                            "Open Access": open_access_status,
                            "URL/DOI": url_doi
                        })
                        
                        collected_items += 1
                        
                        # Aktualisiere Fortschrittsbalken
                        progress_percent = min(collected_items / max_results, 1.0)
                        progress_bar.progress(progress_percent)
                        
                    except Exception as e:
                        st.warning(f"Fehler bei der Verarbeitung einer Publikation: {str(e)}")
                        continue
                
                # Zur nächsten Seite gehen
                current_page += 1
                
                # Kurze Pause zwischen den Anfragen (API-Limit beachten)
                time.sleep(0.5)
                
            except requests.exceptions.RequestException as e:
                st.error(f"Netzwerkfehler bei Seite {current_page}: {str(e)}")
                break
        
        # Daten als DataFrame zurückgeben
        if results:
            status_text.text(f"Verarbeitung abgeschlossen: {len(results)} Publikationen gefunden!")
            df = pd.DataFrame(results)
            
            # Lokale Nachsortierung für komplexere Sortierlogik
            if sort_by["secondary"] != "Keine":
                # Bei kombinierten Sortierkriterien noch einmal lokal sortieren
                # um sicherzustellen, dass die mehrstufige Sortierung korrekt ist
                
                # Spalten für die Sortierung definieren
                sort_columns = []
                sort_ascending = []
                
                # Primäres Sortierkriterium
                if sort_by["primary"] == "Aktualität":
                    sort_columns.append("Jahr")
                    sort_ascending.append(False)  # Absteigend = neueste zuerst
                elif sort_by["primary"] == "Zitationen":
                    sort_columns.append("Zitationen")
                    sort_ascending.append(False)  # Absteigend = meiste zuerst
                
                # Sekundäres Sortierkriterium
                if sort_by["secondary"] == "Aktualität":
                    sort_columns.append("Jahr")
                    sort_ascending.append(False)  # Absteigend = neueste zuerst
                elif sort_by["secondary"] == "Zitationen":
                    sort_columns.append("Zitationen")
                    sort_ascending.append(False)  # Absteigend = meiste zuerst
                
                # Wenn wir tatsächlich lokale Sortierkriterien haben
                if sort_columns:
                    df = df.sort_values(by=sort_columns, ascending=sort_ascending)
            
            return df
        else:
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Fehler bei der Suche: {str(e)}")
        if DEBUG:
            import traceback
            debug_info.code(traceback.format_exc())
        return None
    
    finally:
        progress_bar.empty()
        status_text.empty()
        if not DEBUG:
            debug_info.empty()

def main():
    st.title("📚 Wissenschaftliche Literaturrecherche")
    
    st.write("""
    Geben Sie Schlüsselwörter ein und verfeinern Sie Ihre Suche mit den Filteroptionen.
    Die Ergebnisse werden als Excel-Datei zum Download bereitgestellt.
    """)
    
    # Suchparameter
    keywords = st.text_input("Schlüsselwörter eingeben", "")
    
    # Filter in Seitenleiste platzieren
    st.sidebar.title("Suchfilter")
    
    # Jahresfilter
    st.sidebar.subheader("Publikationsjahr")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_year = st.number_input("Von Jahr", value=2018, min_value=1800, max_value=datetime.now().year)
    with col2:
        end_year = st.number_input("Bis Jahr", value=datetime.now().year, min_value=1800, max_value=datetime.now().year)
    
    # Dokumenttyp-Filter
    st.sidebar.subheader("Dokumenttyp")
    doc_types = st.sidebar.multiselect(
        "Dokumenttypen",
        options=["article", "book", "book-chapter", "dissertation", "journal", "proceedings", "report"],
        default=["article"]
    )
    
    # Open Access Filter
    st.sidebar.subheader("Zugangsart")
    open_access_filter = st.sidebar.radio(
        "Zugangsart wählen",
        options=["Alle", "Open Access", "Kostenpflichtig"],
        index=0
    )
    
    # Sortierung - mehrstufig
    st.sidebar.subheader("Sortieren nach")
    st.sidebar.write("Priorität der Sortierkriterien")
    
    # Erste Priorität
    sort_primary = st.sidebar.selectbox(
        "1. Sortierkriterium",
        options=["Aktualität", "Relevanz", "Zitationen"],
        index=0
    )
    
    # Zweite Priorität
    sort_secondary = st.sidebar.selectbox(
        "2. Sortierkriterium (optional)",
        options=["Keine", "Aktualität", "Relevanz", "Zitationen"],
        index=0
    )
    
    # Maximale Ergebnisse
    st.sidebar.subheader("Maximale Ergebnisanzahl")
    max_results = st.sidebar.slider(
        "Maximale Anzahl der Ergebnisse",
        min_value=20,
        max_value=500,
        value=100,
        step=20
    )
    
    # Suche starten
    if st.button("Suche starten", type="primary"):
        if keywords:
            with st.spinner("Suche läuft..."):
                df = get_publication_data(keywords, start_year, end_year, doc_types, open_access_filter, 
                                       {"primary": sort_primary, "secondary": sort_secondary}, max_results)
                
                if df is not None and not df.empty:
                    st.session_state['search_results'] = df
                    st.success(f"{len(df)} relevante Publikationen gefunden!")
                    
                    # Show results in the app
                    st.subheader("Gefundene Publikationen")
                    st.dataframe(df)
                    
                    # Datei erstellen ohne zu speichern (im Speicher halten)
                    excel_file = f"literaturrecherche_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    output.seek(0)
                    
                    # Provide download button
                    st.download_button(
                        label="Excel-Datei herunterladen",
                        data=output,
                        file_name=excel_file,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Keine Ergebnisse gefunden.")
        else:
            st.warning("Bitte geben Sie Schlüsselwörter ein.")

if __name__ == "__main__":
    main()