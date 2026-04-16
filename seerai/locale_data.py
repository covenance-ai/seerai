"""Per-locale mock data configs (language + country + industry).

Each locale picks an industry that's typical for the country:
  en / US → Software & SaaS (kept for backward compat with the existing
                             English snapshot — Acme Corp / Initech)
  de / DE → Automotive (Kraftwerk Motoren / Rhein Automotive)
  it / IT → Fashion & Luxury Goods (Moda Milano / Atelier Romano)

Consumed by ``scripts/generate_locale_data.py`` to write
``data/snapshot.<lang>.json``. The backend picks the right snapshot file
based on the ``X-Seerai-Lang`` request header.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LocaleConfig:
    """All locale-specific parameters needed to synthesize a snapshot.

    Fields mirror the structures in ``scripts/mock_data.py`` but parameterized
    per locale so we can generate English, German, and Italian datasets that
    look native end-to-end (orgs, users, messages, insight copy).
    """

    lang: str          # "en", "de", "it"
    country: str       # "US", "DE", "IT"
    industry: str      # human-readable
    currency: str      # "USD", "EUR", "EUR"

    # Org tree — same shape as the ORG_TREE dict in mock_data.py.
    org_tree: dict

    # Leaf-org → [user_id] mapping. User IDs go into URLs, so stick to
    # ASCII lowercase.name form (avoid umlauts/accents in IDs).
    users: dict[str, list[str]]

    # User IDs that should receive the "exec" role (org dashboard access).
    execs: set[str]

    # Hourly rate range per org in *local currency*. The dashboard shows
    # the symbol $ vs € via the currency field.
    hourly_rates: dict[str, tuple[int, int]]

    # Human-readable display names (localized). Keys = user_id.
    # Purely cosmetic — optional. If empty, we fall back to user_id.
    display_names: dict[str, str] = field(default_factory=dict)

    # Prompts a user might send in this language/industry.
    user_messages: list[str] = field(default_factory=list)

    # AI replies, ideally relevant to user_messages (same order or random).
    ai_responses: list[str] = field(default_factory=list)

    # Rare error events.
    error_messages: list[str] = field(default_factory=list)

    # Archetype conversations — fully-written multi-turn transcripts so the
    # session-detail page has native content even for "useful" / "trivial"
    # stub sessions. Each archetype is a dict:
    #   {"provider": "anthropic", "utility": "useful",
    #    "turns": [("user", "..."), ("ai", "..."), ...]}
    archetypes: list[dict] = field(default_factory=list)

    # Pre-written cross_department_interest insight seeds (localized).
    cross_dept: list[dict] = field(default_factory=list)

    # Root-org branding (color + 1-letter badge) so the sidebar avatar
    # lands on a recognizable color per company.
    company_brands: dict[str, dict] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────
# EN / US / Software & SaaS (existing English dataset, re-declared here
# for completeness — if someone wipes snapshot.json this regenerates it).
# ────────────────────────────────────────────────────────────────────────

EN_LOCALE = LocaleConfig(
    lang="en",
    country="US",
    industry="Software / SaaS",
    currency="USD",
    org_tree={
        "acme": {
            "name": "Acme Corp",
            "children": {
                "acme-eng": {
                    "name": "Engineering",
                    "children": {
                        "acme-eng-backend": {"name": "Backend"},
                        "acme-eng-frontend": {"name": "Frontend"},
                        "acme-eng-infra": {"name": "Infrastructure"},
                    },
                },
                "acme-product": {
                    "name": "Product",
                    "children": {
                        "acme-product-design": {"name": "Design"},
                        "acme-product-research": {"name": "Research"},
                    },
                },
                "acme-sales": {"name": "Sales"},
            },
        },
        "initech": {
            "name": "Initech",
            "children": {
                "initech-rd": {
                    "name": "R&D",
                    "children": {"initech-rd-ml": {"name": "Machine Learning"}},
                },
                "initech-ops": {"name": "Operations"},
            },
        },
    },
    users={
        "acme-eng-backend": [
            "alice.johnson", "bob.martinez", "carol.chen",
            "dave.wilson", "eve.kim",
        ],
        "acme-eng-frontend": ["frank.lopez", "grace.patel", "henry.nguyen"],
        "acme-eng-infra": ["iris.brown", "jack.taylor"],
        "acme-product-design": ["kate.davis", "liam.moore", "mia.anderson"],
        "acme-product-research": ["noah.thomas", "olivia.jackson"],
        "acme-sales": ["peter.white", "quinn.harris", "rachel.martin", "sam.garcia"],
        "initech-rd-ml": ["tina.clark", "uma.lewis", "victor.hall"],
        "initech-ops": ["wendy.young", "xander.king"],
    },
    execs={"alice.johnson", "kate.davis", "peter.white", "tina.clark"},
    hourly_rates={
        "acme-eng-backend": (60, 120),
        "acme-eng-frontend": (55, 110),
        "acme-eng-infra": (65, 130),
        "acme-product-design": (50, 100),
        "acme-product-research": (55, 105),
        "acme-sales": (35, 75),
        "initech-rd-ml": (70, 140),
        "initech-ops": (40, 80),
    },
    user_messages=[
        "Can you explain how GDPR consent requirements work?",
        "What are the key differences between DPIA and PIA?",
        "Help me draft a data processing agreement for our vendor.",
        "Review this privacy policy section for compliance issues.",
        "What data retention periods does GDPR recommend?",
        "Explain the right to erasure and its exceptions.",
        "How should we handle a data breach notification?",
        "What are the requirements for cross-border data transfers?",
        "Can you summarize Article 35 of GDPR for me?",
        "Help me create a record of processing activities.",
        "Explain the legal bases for processing personal data.",
        "How do we implement privacy by design in our system?",
        "What counts as personal data under GDPR?",
        "Draft an email template for data breach notification.",
    ],
    ai_responses=[
        "Under GDPR, consent must be freely given, specific, informed, and unambiguous. Pre-ticked boxes are not valid consent.",
        "A DPIA (GDPR Art. 35) is required when processing is likely to result in high risk. A PIA is a broader, less prescriptive assessment.",
        "Here's a draft DPA covering Art. 28 duties: purpose limitation, security measures, sub-processor management, audit rights, deletion.",
        "Three issues: (1) the lawful basis isn't stated, (2) retention periods are missing, (3) the right to lodge a complaint isn't mentioned.",
        "GDPR doesn't prescribe retention periods. Retain only as long as necessary, and document justifications per data category.",
        "Art. 17 grants the right to erasure. Exceptions: legal obligations, public interest, archiving, legal-claim establishment/defence.",
        "Arts. 33-34: notify the supervisory authority within 72h; notify data subjects directly if the breach poses high risk.",
        "Post-Schrems II: adequacy decisions, SCCs with supplementary measures, or BCRs. Transfer Impact Assessments are expected.",
        "Art. 35 requires a DPIA for systematic profiling with significant effects, large-scale special-category processing, or public-area monitoring.",
        "A ROPA (Art. 30) lists purposes, data categories, recipients, transfers, retention periods, and security measures.",
    ],
    error_messages=[
        "Rate limit exceeded. Please try again in 30 seconds.",
        "Context window exceeded. Consider breaking your request into smaller parts.",
        "Service temporarily unavailable. The model is being updated.",
        "Invalid input: message exceeds maximum token length.",
    ],
    cross_dept=[
        {
            "user_id": "peter.white",
            "target_org_id": "acme-eng-backend",
            "target_dept": "Backend Engineering",
            "topics": "API architecture, database optimization, and microservice patterns",
            "priority": 2,
        },
        {
            "user_id": "frank.lopez",
            "target_org_id": "initech-rd-ml",
            "target_dept": "Machine Learning",
            "topics": "neural network architectures, model training pipelines, and ML deployment",
            "priority": 3,
        },
        {
            "user_id": "iris.brown",
            "target_org_id": "acme-product-design",
            "target_dept": "Product Design",
            "topics": "user experience patterns, design systems, and accessibility standards",
            "priority": 4,
        },
        {
            "user_id": "noah.thomas",
            "target_org_id": "acme-eng-infra",
            "target_dept": "Infrastructure",
            "topics": "container orchestration, CI/CD pipelines, and cloud architecture",
            "priority": 3,
        },
    ],
    company_brands={
        "acme":    {"name": "Acme Corp", "color": "#3B82F6", "initial": "A"},
        "initech": {"name": "Initech",   "color": "#10B981", "initial": "I"},
    },
    archetypes=[
        {
            "provider": "anthropic",
            "utility": "useful",
            "turns": [
                ("user", "I need to draft a data processing agreement for a new analytics vendor handling EU customer data. What clauses are essential?"),
                ("ai",   "An Art. 28 GDPR DPA must cover: (1) subject matter and duration of processing, (2) purpose and nature, (3) obligation of confidentiality for staff, (4) Art. 32 security measures, (5) sub-processor management (prior authorisation + flow-down), (6) assistance with data-subject rights, (7) audit rights, (8) deletion or return of data at contract end, (9) breach notification timelines. For US sub-processors, add SCC Module 3 and a TIA."),
                ("user", "Can you draft the sub-processor clause specifically?"),
                ("ai",   "Sub-processor clause draft: 'Processor shall not engage any sub-processor without Controller's prior written authorisation. Processor shall maintain a list of sub-processors at [URL] and notify Controller at least 30 days before any change, during which Controller may object on reasonable grounds; if not resolved, Controller may terminate the relevant processing activities. Processor shall impose on each sub-processor the same data-protection obligations as in this DPA by way of a written contract, and shall remain fully liable for the performance of its sub-processors.'"),
            ],
        },
        {
            "provider": "openai",
            "utility": "useful",
            "turns": [
                ("user", "How do I structure a breach notification to the ICO within the 72-hour window?"),
                ("ai",   "The ICO's online form asks for: (1) contact details, (2) a description of the nature of the breach, (3) categories and approximate number of data subjects and records, (4) likely consequences, (5) measures taken or proposed. If you don't have full details within 72h, file what you have and mark it preliminary — you can update as the investigation progresses. Maintain an internal breach log (Art. 33(5)) regardless of whether you notify."),
                ("user", "Do we need to notify affected individuals as well?"),
                ("ai",   "Under Art. 34 you must notify data subjects directly only if the breach is likely to result in a high risk to their rights and freedoms. Exceptions: (a) the data was rendered unintelligible to unauthorised parties (e.g. strong encryption where the key wasn't compromised), (b) you've taken subsequent measures making the high risk no longer likely, (c) it would involve disproportionate effort — in which case, public communication is acceptable."),
            ],
        },
        {
            "provider": "google",
            "utility": "trivial",
            "turns": [
                ("user", "What's the penalty ceiling for a GDPR Art. 5 violation?"),
                ("ai",   "Art. 5 violations fall under the higher tier: up to €20M or 4% of worldwide annual turnover, whichever is greater (Art. 83(5))."),
            ],
        },
        {
            "provider": "mistral",
            "utility": "non_work",
            "turns": [
                ("user", "what's a good lunch spot near king's cross?"),
                ("ai",   "A few solid options within a 5-minute walk of King's Cross: Dishoom (Indian breakfast/lunch, be ready to queue), Caravan (brunch-leaning, good filter coffee), and Vinoteca (wine bar with a proper lunch menu). For something quicker, the bakeries inside Coal Drops Yard do decent sandwiches."),
            ],
        },
        {
            "provider": "anthropic",
            "utility": "trivial",
            "turns": [
                ("user", "Quick: DPIA or PIA for a new HR analytics tool processing performance data?"),
                ("ai",   "Sounds like a DPIA is required — HR performance analytics is systematic profiling of employees with potentially significant effects, which is an Art. 35 trigger. Document: (1) description of processing, (2) necessity and proportionality, (3) risks to data subjects, (4) measures to address those risks. Consult your DPO before launch."),
            ],
        },
    ],
)


# ────────────────────────────────────────────────────────────────────────
# DE / Germany / Automotive
# ────────────────────────────────────────────────────────────────────────

DE_LOCALE = LocaleConfig(
    lang="de",
    country="DE",
    industry="Automobilindustrie",
    currency="EUR",
    org_tree={
        "kraftwerk": {
            "name": "Kraftwerk Motoren AG",
            "children": {
                "kraftwerk-antrieb": {
                    "name": "Antriebsentwicklung",
                    "children": {
                        "kraftwerk-antrieb-verbrenner": {"name": "Verbrennungsmotor"},
                        "kraftwerk-antrieb-ebatterie":  {"name": "E-Batterie"},
                        "kraftwerk-antrieb-hybrid":     {"name": "Hybrid"},
                    },
                },
                "kraftwerk-elektronik": {
                    "name": "Fahrzeugelektronik",
                    "children": {
                        "kraftwerk-elektronik-steuergeraet": {"name": "Steuergeräte"},
                        "kraftwerk-elektronik-adas":         {"name": "ADAS"},
                    },
                },
                "kraftwerk-vertrieb": {"name": "Vertrieb"},
            },
        },
        "rhein": {
            "name": "Rhein Automotive GmbH",
            "children": {
                "rhein-forschung": {
                    "name": "Forschung",
                    "children": {
                        "rhein-forschung-autonom": {"name": "Autonomes Fahren"},
                    },
                },
                "rhein-produktion": {"name": "Produktion"},
            },
        },
    },
    users={
        "kraftwerk-antrieb-verbrenner": [
            "stefan.mueller", "klaus.bauer", "anja.schmidt",
            "maximilian.weber", "sophie.fischer",
        ],
        "kraftwerk-antrieb-ebatterie": ["markus.wagner", "julia.becker", "lars.hoffmann"],
        "kraftwerk-antrieb-hybrid":    ["franziska.richter", "thomas.koch"],
        "kraftwerk-elektronik-steuergeraet": ["matthias.schulz", "laura.wolf", "jonas.meier"],
        "kraftwerk-elektronik-adas":   ["nicole.schneider", "fabian.schwarz"],
        "kraftwerk-vertrieb": [
            "oliver.braun", "katharina.krause",
            "sebastian.zimmermann", "christina.neumann",
        ],
        "rhein-forschung-autonom": ["martin.huber", "eva.schuster", "philipp.lang"],
        "rhein-produktion":        ["barbara.jansen", "andreas.fuchs"],
    },
    execs={"stefan.mueller", "matthias.schulz", "oliver.braun", "martin.huber"},
    hourly_rates={
        "kraftwerk-antrieb-verbrenner":       (55, 105),
        "kraftwerk-antrieb-ebatterie":        (65, 125),
        "kraftwerk-antrieb-hybrid":           (60, 115),
        "kraftwerk-elektronik-steuergeraet":  (60, 115),
        "kraftwerk-elektronik-adas":          (70, 135),
        "kraftwerk-vertrieb":                 (40, 80),
        "rhein-forschung-autonom":            (75, 140),
        "rhein-produktion":                   (35, 75),
    },
    display_names={
        "stefan.mueller": "Stefan Müller", "klaus.bauer": "Klaus Bauer",
        "anja.schmidt": "Anja Schmidt", "maximilian.weber": "Maximilian Weber",
        "sophie.fischer": "Sophie Fischer", "markus.wagner": "Markus Wagner",
        "julia.becker": "Julia Becker", "lars.hoffmann": "Lars Hoffmann",
        "franziska.richter": "Franziska Richter", "thomas.koch": "Thomas Koch",
        "matthias.schulz": "Matthias Schulz", "laura.wolf": "Laura Wolf",
        "jonas.meier": "Jonas Meier", "nicole.schneider": "Nicole Schneider",
        "fabian.schwarz": "Fabian Schwarz", "oliver.braun": "Oliver Braun",
        "katharina.krause": "Katharina Krause",
        "sebastian.zimmermann": "Sebastian Zimmermann",
        "christina.neumann": "Christina Neumann", "martin.huber": "Martin Huber",
        "eva.schuster": "Eva Schuster", "philipp.lang": "Philipp Lang",
        "barbara.jansen": "Barbara Jansen", "andreas.fuchs": "Andreas Fuchs",
    },
    user_messages=[
        "Wie wirkt sich die neue EU-Typgenehmigung (UNECE R155) auf unsere ECU-Software aus?",
        "Können Sie unsere ISO-26262-ASIL-D-Dokumentation für das Bremssteuergerät prüfen?",
        "Wie diagnostiziere ich sporadische CAN-Bus-Fehler zwischen BCM und Getriebesteuergerät?",
        "Erstellen Sie einen BMS-Kalibrierungsplan für die 800-V-Lithium-Ionen-Batterie.",
        "Welche EMV-Anforderungen gelten für unsere Ladeelektronik nach CISPR 25?",
        "Fassen Sie den Cybersecurity-Lebenszyklus nach ISO 21434 zusammen.",
        "Entwerfen Sie einen Prüfplan für die ADAS-Radar-Sensorfusion bei 140 km/h.",
        "Wie implementieren wir OTA-Updates mit Secure Boot auf dem Hauptsteuergerät?",
        "Erklären Sie den Unterschied zwischen ASIL B und ASIL D im Kontext unseres Lenkungs-Steuergeräts.",
        "Welche Wartungsintervalle empfehlen Sie für unsere Prüfstandsroboter?",
        "Wie reduzieren wir den NOx-Ausstoß beim WLTP-Prüfzyklus ohne Leistungsverlust?",
        "Entwerfen Sie ein FMEA-Sheet für die Hochvolt-Batteriepack-Montage.",
        "Welche Änderungen bringt Euro 7 für unseren Benzin-Direkteinspritzer?",
        "Wie integriere ich V2X-Kommunikation (C-V2X PC5) in unser Connectivity-Steuergerät?",
    ],
    ai_responses=[
        "UNECE R155 schreibt ein zertifiziertes Cybersecurity-Managementsystem (CSMS) vor. Ihre ECU-Software muss über den gesamten Lebenszyklus (Entwicklung, Produktion, Nachlauf) Bedrohungsanalysen, Risikoabschätzungen und nachweisbare Schutzmaßnahmen dokumentieren. Ohne CSMS-Zertifikat keine Typgenehmigung ab 07/2024.",
        "Die ASIL-D-Dokumentation für das Bremssteuergerät sollte Folgendes enthalten: (1) Safety Goals mit HARA-Ableitung, (2) Technical Safety Concept mit Redundanzstrategie, (3) Software-Architektur mit FFI-Analyse, (4) Verifikationsplan auf Unit-, Integrations- und Systemebene, (5) ISO-26262-Teil-8-Confirmation-Measures-Matrix.",
        "Sporadische CAN-Fehler zwischen BCM und TCU deuten meist auf Buslastspitzen, defekte Busabschlüsse (120 Ω fehlend) oder schlechte Masseverbindung hin. Prüfen Sie mit einem CAN-Oszilloskop: (1) Recessive-Pegel stabil bei 2,5 V, (2) keine Kollisionen im DTC-Fenster, (3) Buslast unter 60 %.",
        "Ein BMS-Kalibrierungsplan für 800-V-Li-Ion deckt ab: SOC-Schätzung über OCV-Lookup + Coulomb-Counting, SOH über interne Widerstandsmessung alle 1000 Zyklen, Zellbalancing bei Δ > 30 mV, Temperaturderating ab 45 °C, Isolationswiderstand > 100 Ω/V.",
        "Nach CISPR 25 Klasse 5 muss Ihre Ladeelektronik im 150 kHz–108 MHz-Bereich leitungsgebundene Störungen unter 50 dBµV halten. Typische Maßnahmen: Gleichtaktdrosseln am DC-Eingang, geschirmte Leitungen zum Onboard-Charger, Masseflächen auf der Steuerungs-Leiterplatte.",
        "ISO 21434 definiert einen Cybersecurity-Lebenszyklus in vier Phasen: (1) Concept (TARA, Assets, Threats, Risks), (2) Product Development (Secure Coding, Vulnerability Management), (3) Post-Development (Production, Operations), (4) End-of-Life. Jede Phase liefert dokumentierte Artefakte für die R155-Typgenehmigung.",
        "Ein Prüfplan für ADAS-Radar-Sensorfusion bei 140 km/h sollte folgende Szenarien abdecken: Auffahrtest auf stehendes Fahrzeug (EuroNCAP CCRs), Querverkehr bei Kreuzung, Spurwechselerkennung mit 3σ Latency-Budget < 100 ms. Zusätzlich FMCW-Radar-Interferenztest mit benachbartem 77-GHz-Modul.",
        "Secure-Boot-OTA auf dem Haupt-SG: Die Bootloader-Signatur wird durch einen OEM-Root-Key in der HSM verifiziert (ED25519, 256 Bit). Das A/B-Partitionsschema erlaubt Rollback bei fehlgeschlagenem Post-Flash-Self-Test. Integritätsprüfung vor jedem Start über SHA-256.",
        "ASIL B verlangt 90 % Single-Point-Fault-Metric und 60 % Latent-Fault-Metric; ASIL D verlangt 99 % bzw. 90 %. Für das Lenkungs-SG bedeutet das: Redundante Sensoren mit plausibilisiertem Quervergleich, zwei unabhängige Mikrocontroller im Lock-Step, CRC-geschützte Kommunikation.",
        "Für Prüfstandsroboter im Motor- bzw. Getriebetest empfehlen sich: (1) Wöchentliche Achsen-Kalibrierung, (2) Quartalsweise Spindelöl-Analyse, (3) Halbjährlicher Abgleich der Drehmomentsensoren, (4) Jährlicher Austausch der Greiferbacken bei hochbelasteten Zellen.",
    ],
    error_messages=[
        "Ratenbegrenzung überschritten. Bitte in 30 Sekunden erneut versuchen.",
        "Kontextfenster überschritten. Bitte die Anfrage in kleinere Teile zerlegen.",
        "Dienst vorübergehend nicht verfügbar. Das Modell wird aktualisiert.",
        "Ungültige Eingabe: Nachricht überschreitet maximale Tokenlänge.",
    ],
    cross_dept=[
        {
            "user_id": "oliver.braun",
            "target_org_id": "kraftwerk-antrieb-ebatterie",
            "target_dept": "E-Batterie-Entwicklung",
            "topics": "Zellchemie, Schnellladekurven und Reichweitenmarketing",
            "priority": 2,
        },
        {
            "user_id": "matthias.schulz",
            "target_org_id": "rhein-forschung-autonom",
            "target_dept": "Autonomes Fahren",
            "topics": "LiDAR-Sensorfusion, HD-Karten und Sicherheitsfreigabe nach SOTIF",
            "priority": 3,
        },
        {
            "user_id": "barbara.jansen",
            "target_org_id": "kraftwerk-elektronik-adas",
            "target_dept": "ADAS",
            "topics": "Kamera-Kalibrierung, End-of-Line-Prüfung und Produktionstaktung",
            "priority": 4,
        },
        {
            "user_id": "julia.becker",
            "target_org_id": "kraftwerk-antrieb-verbrenner",
            "target_dept": "Verbrennungsmotor",
            "topics": "Hybridintegration, Thermomanagement und Euro-7-Anforderungen",
            "priority": 3,
        },
    ],
    company_brands={
        "kraftwerk": {"name": "Kraftwerk Motoren AG", "color": "#1F2937", "initial": "K"},
        "rhein":     {"name": "Rhein Automotive",     "color": "#0EA5E9", "initial": "R"},
    },
    archetypes=[
        {
            "provider": "anthropic",
            "utility": "useful",
            "turns": [
                ("user", "Ich entwickle die Software für unser neues Batteriemanagementsystem (800 V). Wie implementieren wir eine sichere Zellbalancierung, die ISO 26262 ASIL C erfüllt?"),
                ("ai",   "Für ASIL-C-konformes aktives Zellbalancing brauchen Sie: (1) Redundante Zellspannungsmessung mit Plausibilisierung (zwei unabhängige ICs pro 12-Zell-Modul, Quervergleich < 10 mV). (2) Hardware-Überwachung des Balancing-MOSFETs — Strommessung je Zelle und Safe-Shutdown bei > 50 ms überhöhtem Strom. (3) Software-Watchdog mit Reset-Fenster von 100 ms. (4) Diagnostic Coverage > 97 % für die Balancing-FETs (Latent Fault Metric ≥ 80 %). (5) Q-Manager-Flow: TARA nach ISO 21434 + HARA nach ISO 26262, SPFM ≥ 97 %, LFM ≥ 80 %."),
                ("user", "Und wie testen wir die Plausibilisierung praktisch?"),
                ("ai",   "Praktisch testen Sie in vier Stufen: (a) HIL-Stimulation: Zellspannung eines ICs künstlich um 50 mV verschieben und prüfen, ob der Fehler innerhalb 20 ms erkannt wird. (b) Fault-Injection am Kommunikationsbus (daisy-chain SPI) — Bitfehler einspeisen und CRC-Erkennung validieren. (c) Umwelt-Tests nach AEC-Q100: Temperaturbereich -40 °C bis +85 °C, Vibration IEC 60068-2-6. (d) Langzeit-Dauerlauf 2000 h im Klimaschrank mit realistischem Lastprofil aus Kundenfahrzeugen."),
            ],
        },
        {
            "provider": "openai",
            "utility": "useful",
            "turns": [
                ("user", "Wir bekommen sporadisch CAN-Bus-Fehler zwischen dem Bremssteuergerät und dem ESP-Modul. Die Fehler treten nur bei Temperaturen über 60 °C auf. Was könnte das sein?"),
                ("ai",   "Temperaturabhängige sporadische CAN-Fehler deuten typischerweise auf eine dieser Ursachen hin: (1) Degradierte Lötstellen am CAN-Transceiver — thermische Ausdehnung öffnet Mikrorisse. Per Mikroskop/Röntgen prüfen. (2) Masseschleife durch schlechten Chassis-Kontakt, die sich bei Erwärmung verändert. Multimetermessung ΔR zwischen BCM-Masse und ESP-Masse vor/nach Erwärmung. (3) Terminierungswiderstand drift — nominal 120 Ω, aber ab 60 °C > 130 Ω → Reflexionen. Nachmessen mit Oszilloskop. (4) Clock-Skew beim Quarz des ESP-Moduls — ppm-Abweichung bei Temperatur führt zu Bit-Timing-Fehlern. Häufigkeit der Error-Frames vs. Temperatur loggen."),
                ("user", "Wie priorisiere ich die Ursachenforschung?"),
                ("ai",   "Priorisierung nach Aufwand × Wahrscheinlichkeit: Zuerst (3) Terminierung — 15 min mit Scope. Dann (2) Masseschleife — 30 min Multimeter. Dann (1) Lötstellen — 2 h Demontage + Röntgen. Zuletzt (4) Clock-Skew — Entwicklungsumgebung nötig. Starten Sie parallel mit einem Temperatur-Trace des CAN-Fehlerzählers über 1 h im Klimaschrank, das engt schon ein."),
            ],
        },
        {
            "provider": "google",
            "utility": "trivial",
            "turns": [
                ("user", "Kurze Frage: Ab wann gilt Euro 7 für neue Pkw?"),
                ("ai",   "Euro 7 gilt ab dem 1. Juli 2025 für neue Pkw-Typgenehmigungen und ab dem 1. Juli 2026 für alle Neuzulassungen. Für Nutzfahrzeuge verschiebt sich das um jeweils 24 Monate."),
            ],
        },
        {
            "provider": "mistral",
            "utility": "non_work",
            "turns": [
                ("user", "wo ist der beste Kaffee in der Nähe von Werk 2?"),
                ("ai",   "Rund um Werk 2 empfehlen sich drei Spots innerhalb von 10 Gehminuten: 'Rösterei am Wasserturm' (klassisch, gute Filter), 'Café Hellblau' (Specialty, schöne Terrasse) und der Bäckerei-Shop gegenüber dem Pförtnerhaus (schneller, solide Qualität zum Mitnehmen)."),
            ],
        },
        {
            "provider": "anthropic",
            "utility": "trivial",
            "turns": [
                ("user", "Kurzfrage: DPIA oder nur Art. 30-Eintrag für ein neues Fahrzeugflottentelemetrie-Tool?"),
                ("ai",   "Flottentelemetrie = systematische Ortung von Fahrern → DPIA nach Art. 35 DSGVO erforderlich. Dokumentieren Sie: Zweck + Notwendigkeit, Datenkategorien (GPS, Geschwindigkeit, Fahrer-ID), Risiken (Bewegungsprofil), Schutzmaßnahmen (Pseudonymisierung, Retention max. 30 Tage, Opt-out in Dienstanweisung). Betriebsrat beteiligen."),
            ],
        },
    ],
)


# ────────────────────────────────────────────────────────────────────────
# IT / Italy / Fashion & Luxury
# ────────────────────────────────────────────────────────────────────────

IT_LOCALE = LocaleConfig(
    lang="it",
    country="IT",
    industry="Moda e Lusso",
    currency="EUR",
    org_tree={
        "moda": {
            "name": "Moda Milano S.p.A.",
            "children": {
                "moda-design": {
                    "name": "Design",
                    "children": {
                        "moda-design-prontomoda": {"name": "Pronto moda"},
                        "moda-design-altamoda":   {"name": "Alta moda"},
                    },
                },
                "moda-produzione": {
                    "name": "Produzione",
                    "children": {
                        "moda-produzione-tessitura":  {"name": "Tessitura"},
                        "moda-produzione-confezione": {"name": "Confezionamento"},
                    },
                },
                "moda-vendite": {"name": "Vendite"},
            },
        },
        "atelier": {
            "name": "Atelier Romano",
            "children": {
                "atelier-marketing": {
                    "name": "Marketing",
                    "children": {
                        "atelier-marketing-digitale": {"name": "Digitale"},
                    },
                },
                "atelier-boutique": {"name": "Boutique"},
            },
        },
    },
    users={
        "moda-design-prontomoda": [
            "giulia.rossi", "marco.ferrari", "alessia.romano",
            "luca.colombo", "chiara.bianchi",
        ],
        "moda-design-altamoda":   ["federica.ricci", "matteo.marino", "elena.greco"],
        "moda-produzione-tessitura":  ["sofia.costa", "lorenzo.conti"],
        "moda-produzione-confezione": [
            "valentina.esposito", "antonio.leone", "martina.fontana",
        ],
        "moda-vendite": [
            "davide.gatti", "francesca.serra", "roberto.villa", "ilaria.longo",
        ],
        "atelier-marketing-digitale": ["paola.galli", "giuseppe.santoro", "silvia.mancini"],
        "atelier-boutique":           ["leonardo.riva", "camilla.pellegrini"],
    },
    execs={"giulia.rossi", "federica.ricci", "davide.gatti", "paola.galli"},
    hourly_rates={
        "moda-design-prontomoda":     (45, 90),
        "moda-design-altamoda":       (65, 130),
        "moda-produzione-tessitura":  (30, 60),
        "moda-produzione-confezione": (28, 55),
        "moda-vendite":               (35, 75),
        "atelier-marketing-digitale": (45, 95),
        "atelier-boutique":           (28, 55),
    },
    display_names={
        "giulia.rossi": "Giulia Rossi", "marco.ferrari": "Marco Ferrari",
        "alessia.romano": "Alessia Romano", "luca.colombo": "Luca Colombo",
        "chiara.bianchi": "Chiara Bianchi", "federica.ricci": "Federica Ricci",
        "matteo.marino": "Matteo Marino", "elena.greco": "Elena Greco",
        "sofia.costa": "Sofia Costa", "lorenzo.conti": "Lorenzo Conti",
        "valentina.esposito": "Valentina Esposito",
        "antonio.leone": "Antonio Leone", "martina.fontana": "Martina Fontana",
        "davide.gatti": "Davide Gatti", "francesca.serra": "Francesca Serra",
        "roberto.villa": "Roberto Villa", "ilaria.longo": "Ilaria Longo",
        "paola.galli": "Paola Galli", "giuseppe.santoro": "Giuseppe Santoro",
        "silvia.mancini": "Silvia Mancini", "leonardo.riva": "Leonardo Riva",
        "camilla.pellegrini": "Camilla Pellegrini",
    },
    user_messages=[
        "Come posso costruire una tech pack per una giacca in seta stampata per la collezione PE26?",
        "Qual è la procedura corretta per il grading di taglie dal 38 al 48 sul cartamodello?",
        "Suggeriscimi una palette Pantone ispirata alla costa amalfitana per la collezione estiva.",
        "Come gestiamo la tracciabilità GOTS per il nostro cotone organico dal campo al capo?",
        "Draft di un brief per la sfilata di Milano Fashion Week a febbraio.",
        "Qual è la differenza normativa tra Made in Italy e 100% Made in Italy?",
        "Come proteggiamo il marchio dal dropshipping di contraffazioni su TikTok?",
        "Pianificazione produttiva: come bilanciare pronto moda e collezione capsula?",
        "Quali sono i KPI giusti per una boutique fisica in via Montenapoleone?",
        "Come integrare il chip NFC sotto l'etichetta in pelle per l'anti-contraffazione?",
        "Ottimizza la stagionalità del buying plan per la boutique di Firenze.",
        "Quali sono i costi di lavorazione di un abito da sera in organza plissé?",
        "Come gestire il Digital Product Passport (DPP) previsto dall'UE dal 2027?",
        "Stima i margini lordi di una capsule collection co-branded con un artista emergente.",
    ],
    ai_responses=[
        "Una tech pack completa per giacca in seta stampata richiede: (1) disegno tecnico fronte/retro/interni in scala 1:5, (2) scheda materiali con codice fornitore seta, peso (g/m²) e test di solidità colore, (3) BOM dettagliata fodera/rinforzi/bottoni, (4) punti di misura taglie 38-48, (5) specifica di stampa con file pantone separati, (6) lista controllo qualità con tolleranze.",
        "Il grading 38-48 prevede una scalatura proporzionale: larghezza torace +2 cm per taglia, lunghezza manica +1 cm ogni 2 taglie, giro vita +2 cm. Usate curve differenziate tra 38-42 e 44-48 perché il corpo non scala linearmente. Verificare con tre vestibilità reali prima di approvare il piazzamento industriale.",
        "Palette Amalfi PE26: (1) Blu Costiera #1E4E8C — profondità mare, (2) Giallo Limone #F3D03E — agrumeto, (3) Bianco Maiolica #F4F1E8 — terracotta imbiancata, (4) Rosa Bouganville #D95E80, (5) Verde Ulivo #6B7A3A. Usate il Blu Costiera come base neutra (40 %), gli accenti tropicali al 30 %, i toni terrosi al 30 %.",
        "Per la tracciabilità GOTS end-to-end servono: (1) Transaction Certificate (TC) per ogni passaggio di custodia, (2) Scope Certificate del fornitore di seme, ginnatura, filatura, tessitura e confezione, (3) mass-balance reconciliation ogni trimestre, (4) audit annuale dell'ente certificatore, (5) etichette GOTS con numero di licenza.",
        "Brief Milano Fashion Week (febbraio): tema 'Riflessi Adriatici' — palette blu notte/argento/perla, 22 uscite, cast 16 modelle + 6 modelli. Location Ex Dogana Settala, capienza 380. Sound design originale, 12 minuti totali. Press release in inglese + italiano embargoed fino al giorno show.",
        "Made in Italy (Legge 166/2009): almeno due fasi produttive in Italia tra filatura, tessitura, nobilitazione, confezione. 100% Made in Italy (Legge 55/2010): tutte e quattro le fasi in Italia con materie prime italiane o documentate. La seconda è più restrittiva e tutelata penalmente contro l'abuso.",
        "Contrasto al dropshipping di contraffazioni su TikTok: (1) registrazione marchio nel sistema IP Protection di TikTok Shop, (2) monitoraggio con tool tipo Red Points o Onesight sui 50 hashtag chiave, (3) takedown automatici per listing con prezzo < 30 % del retail, (4) lettere di diffida ai grandi reseller con evidenza fotografica, (5) blocco IBAN tramite polizia postale in caso di volumi > 10k€.",
        "Bilanciamento pronto moda / capsule: destinate il 70 % della capacità ai drop stagionali con lead time 6 settimane, il 20 % alle capsule con lead time 10-12 settimane, il 10 % alle riassortimenti lampo entro 3 settimane. I capsule hanno marginalità +8-12 punti perché prezzi premium, ma aumentano il rischio di rimanenze.",
        "KPI boutique Montenapoleone: conversion rate (visite/scontrini) target 18-22 %, scontrino medio target € 1800-2400, UPT (units per transaction) target 2.1, sell-through settimanale 15-20 %, ritorno per metro quadro € 25-35k/anno, NPS clienti VIP > 70.",
        "Integrazione NFC anti-contraffazione: chip NTAG424 DNA (hardware crypto AES-128) cucito sotto l'etichetta in pelle posteriore. Ogni chip emette un link univoco firmato lato server. L'app consumer verifica la firma e mostra provenienza, materiali e care guide. Costo chip ~€0.40, setup ~€12k una tantum.",
    ],
    error_messages=[
        "Limite di richieste superato. Riprova tra 30 secondi.",
        "Contesto superato. Suddividi la richiesta in parti più piccole.",
        "Servizio temporaneamente non disponibile. Il modello è in aggiornamento.",
        "Input non valido: il messaggio supera il limite massimo di token.",
    ],
    cross_dept=[
        {
            "user_id": "davide.gatti",
            "target_org_id": "moda-design-altamoda",
            "target_dept": "Alta moda",
            "topics": "calendario sfilate, esclusive VIP e pricing strategico",
            "priority": 2,
        },
        {
            "user_id": "paola.galli",
            "target_org_id": "moda-design-prontomoda",
            "target_dept": "Pronto moda",
            "topics": "storytelling stagionale, campagne social e collaborazioni con influencer",
            "priority": 3,
        },
        {
            "user_id": "sofia.costa",
            "target_org_id": "atelier-marketing-digitale",
            "target_dept": "Marketing Digitale",
            "topics": "fotografia di prodotto, schede tecniche web e SEO",
            "priority": 4,
        },
        {
            "user_id": "valentina.esposito",
            "target_org_id": "moda-design-altamoda",
            "target_dept": "Alta moda",
            "topics": "lavorazioni sartoriali, tempi di couture e rifiniture a mano",
            "priority": 3,
        },
    ],
    company_brands={
        "moda":    {"name": "Moda Milano", "color": "#BE123C", "initial": "M"},
        "atelier": {"name": "Atelier Romano", "color": "#CA8A04", "initial": "A"},
    },
    archetypes=[
        {
            "provider": "anthropic",
            "utility": "useful",
            "turns": [
                ("user", "Sto preparando il buying plan PE26 per la nostra boutique di Firenze. Budget 480k€, target margine lordo 62%. Suggerimenti su allocazione per categoria?"),
                ("ai",   "Proposta allocazione PE26 Firenze (turisti + clientela locale fidelizzata):\n- Abiti e completi: 32% (€153k) — top di gamma, margine ~65%\n- Capispalla leggeri: 18% (€86k) — buon ritorno turistico, margine ~60%\n- Camicie e bluse: 12% (€57k) — alto rotazione, margine ~58%\n- Pantaloni/gonne: 14% (€67k) — margine ~62%\n- Maglieria/t-shirt: 10% (€48k) — riassortimenti frequenti, margine ~55%\n- Accessori e pelletteria: 10% (€48k) — impulso, margine ~70%\n- Scarpe: 4% (€19k) — capsule co-branded, margine ~63%\n\nConsideriamo che Firenze pesa forte d'estate sui turisti americani: spingete l'etichetta 'Made in Italy' con pricing premium (+15%) da maggio a settembre. Per il margine 62% vi conviene negoziare tempi di pagamento 90gg con i fornitori di stoffe italiane."),
                ("user", "Come gestisco il rischio di rimanenze sulla maglieria visto che ordiniamo 6 mesi prima?"),
                ("ai",   "Tre leve concrete contro le rimanenze maglieria:\n(1) Ordine iniziale al 60% del forecast, opzione di riassortimento lampo (3-4 settimane) sul 40% con il partner tessile pratese — contratti quadro 'open-to-buy' vi fanno fissare il prezzo senza impegnare volumi.\n(2) Mix 65% colori core stagionali + 35% nuance pilot. Le nuance pilot le ordinate in quantità minima (300 pezzi) per capire la trazione, poi riassortite.\n(3) Markdown cadence ferma: -20% in sesta settimana di saldi, -40% in ottava, outlet o B2B-only in dodicesima. Questo riduce i resi a meno del 12% della stagione. Evitate markdown prima perché erode il tasso di pieno prezzo dei clienti VIP."),
            ],
        },
        {
            "provider": "openai",
            "utility": "useful",
            "turns": [
                ("user", "Dobbiamo integrare il Digital Product Passport UE nella nostra linea pronto moda entro il 2027. Da dove partiamo concretamente?"),
                ("ai",   "Il DPP (Reg. UE 2023/1542 + ESPR) per il tessile diventa obbligatorio a scaglioni tra 2027 e 2030. Roadmap pratica in 5 step:\n1. Assessment dati (Q1/Q2 2026): mappate i dati già presenti nel vostro PLM — BOM, provenienza materie prime, certificazioni, emissioni. Identificate i gap (tipicamente: Tier-3/4 supplier, carbon footprint per capo).\n2. Scelta tecnologica data carrier (Q3 2026): QR dinamico vs NFC NTAG424 DNA. Per pronto moda con rotazione alta il QR serigrafato è più economico (€0.02/capo) ma meno anti-tampering. NFC conviene se prezzo medio > €150.\n3. Backend DPP (Q4 2026): scegliete tra soluzione SaaS (Trustrace, Kezzler, Eon) o build-it-yourself. Per vostri volumi SaaS è ~€2-4/capo/anno, build richiede ~€800k investimento.\n4. Supply chain enablement (H1 2027): contratti con fornitori Tier-1/2 che impongono la trasmissione dei dati DPP (certificati, provenienza, composizione). Audit dei Tier-3/4 critici.\n5. Pilota + rollout (H2 2027): iniziate con una capsule di 200 SKU, validate il passport completo, estendete alla collezione entro 6 mesi.\n\nBudget indicativo: €450-600k nei primi 18 mesi, poi €50-80k/anno di running cost."),
                ("user", "Quale carrier dati scegli tra QR e NFC per la nostra fascia di prezzo (media €200-800)?"),
                ("ai",   "Per €200-800 di price point, QR + NFC ibrido è il compromesso migliore:\n- QR sul cartellino cartaceo visibile al consumatore in fitting room — costo €0.02, scansionabile senza app dedicata.\n- NFC NTAG424 DNA cucito nell'etichetta permanente — costo €0.40 incluso inserimento, resistente a 50 lavaggi. Serve come chiave anti-contraffazione a lungo termine.\n\nIl QR rimanda il consumatore alla scheda DPP per info materiali/origine/manutenzione. L'NFC fornisce firma crittografica univoca verificabile dal retailer o dal secondhand marketplace. Costo marginale totale: €0.42/capo, impatto margine <0.2% al vostro price point."),
            ],
        },
        {
            "provider": "google",
            "utility": "trivial",
            "turns": [
                ("user", "Ricordami: da quando è obbligatoria la EPR tessile in Italia?"),
                ("ai",   "In Italia l'EPR per tessile e calzature è operativa dal 1° gennaio 2022 (D.Lgs. 116/2020, recepimento Direttiva UE 2018/851). I produttori devono iscriversi al Registro nazionale EPR e versare il contributo ambientale al consorzio di riferimento (Re.Crea per il moda)."),
            ],
        },
        {
            "provider": "mistral",
            "utility": "non_work",
            "turns": [
                ("user", "Dove prendo un buon aperitivo vicino allo showroom di via della Spiga?"),
                ("ai",   "A due passi dallo showroom di via della Spiga: (1) Terrazza 12 nel Dedica Anthology Milano — vista sulla Cattedrale, cocktail curati, giacca gradita. (2) Bar Bamboo del Mandarin Oriental — più riservato, drinks stagionali. (3) La Vineria di via Sant'Andrea — enoteca con tagliere di prosciutto di Parma DOP 24 mesi. Prenotate, quel giro è sempre pieno all'aperitivo."),
            ],
        },
        {
            "provider": "anthropic",
            "utility": "trivial",
            "turns": [
                ("user", "Veloce: il 100% Made in Italy richiede anche filati italiani?"),
                ("ai",   "Sì. Il marchio '100% Made in Italy' (L. 55/2010) richiede che tutte le quattro fasi — filatura, tessitura, nobilitazione e confezione — siano svolte in Italia con materie prime italiane o comunque documentate come lavorate in Italia. Lo usate solo se potete provarlo con certificati del filatore."),
            ],
        },
    ],
)


# ────────────────────────────────────────────────────────────────────────
# Registry
# ────────────────────────────────────────────────────────────────────────

LOCALES: dict[str, LocaleConfig] = {
    "en": EN_LOCALE,
    "de": DE_LOCALE,
    "it": IT_LOCALE,
}


def get_locale(lang: str) -> LocaleConfig:
    """Return the locale config for `lang`, defaulting to English."""
    return LOCALES.get(lang, EN_LOCALE)
