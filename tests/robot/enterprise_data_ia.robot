*** Settings ***
Documentation     Parcours E2E réel de l'Enterprise Data & IA Copilot.
...               La suite démarre une stack isolée sur les ports 3100/8100,
...               pilote Chrome et n'utilise aucune donnée mockée.
Library           SeleniumLibrary    timeout=25s
Library           Process
Library           OperatingSystem
Suite Setup       Démarrer la stack Robot
Suite Teardown    Arrêter la stack Robot
Test Tags         e2e    robot-framework


*** Variables ***
${PROJECT_ROOT}       ${CURDIR}${/}..${/}..
${FRONTEND_DIR}       ${PROJECT_ROOT}${/}frontend
${RESULTS_DIR}        ${CURDIR}${/}results
${RUNTIME_DIR}        ${RESULTS_DIR}${/}runtime
${FRONTEND_URL}       http://127.0.0.1:3100
${API_URL}            http://127.0.0.1:8100
${SAMPLE_FILE}        ${PROJECT_ROOT}${/}backend${/}data${/}samples${/}packaging_data.csv
${BROKEN_XLSX}        ${CURDIR}${/}fixtures${/}broken.xlsx
${NON_NUMERIC_FILE}   ${CURDIR}${/}fixtures${/}non_numeric.csv
${NUMERIC_ONLY_FILE}  ${CURDIR}${/}fixtures${/}numeric_only.csv
${PYTHON_COMMAND}     python
${NODE_COMMAND}       node
${ROBOT_SERVER}       ${FRONTEND_DIR}${/}scripts${/}robot-server.mjs
${SERVICE_TOKEN}      robot-backend-service-token-2026-at-least-32-bytes
${ACCESS_PASSWORD}    RobotDemoPassword!2026
${SESSION_SECRET}     robot-session-signing-secret-2026-at-least-32-bytes


*** Test Cases ***
00 - Authentifier la démo sans exposer le backend
    [Documentation]    Vérifie la protection directe de FastAPI, le refus d'un mauvais mot de passe puis une session valide.
    Wait Until Location Contains    /login    20s
    Location Should Contain    next=
    Page Should Contain    Connexion au workspace
    Page Should Contain    Données de démonstration uniquement
    ${frame_policy}=    Evaluate    __import__('httpx').get('${FRONTEND_URL}/login', timeout=5).headers.get('x-frame-options')
    Should Be Equal    ${frame_policy}    DENY
    ${status}=    Evaluate    __import__('httpx').get('${API_URL}/api/overview', timeout=5).status_code
    Should Be Equal As Integers    ${status}    401
    Input Password    css:input[name="password"]    mot-de-passe-incorrect
    Click Button    xpath=//button[normalize-space()="Accéder au workspace"]
    Wait Until Element Contains    css:[role="alert"]    Mot de passe incorrect    10s
    Input Password    css:input[name="password"]    ${ACCESS_PASSWORD}
    Click Button    xpath=//button[normalize-space()="Accéder au workspace"]
    Wait Until Location Is    ${FRONTEND_URL}/    20s

01 - Afficher le dataset de démonstration réel
    [Documentation]    Vérifie les dimensions calculées par FastAPI au démarrage.
    Wait Until Page Contains    Marketing Leads    30s
    Page Should Contain    15 lignes
    Page Should Contain    11 colonnes
    Page Should Contain    Score qualité
    Page Should Contain    Tendance métier

02 - Importer et propager un CSV réel
    [Documentation]    Importe Packaging Data et vérifie l'invalidation globale.
    ${sample_file}=    Normalize Path    ${SAMPLE_FILE}
    File Should Exist    ${sample_file}
    Choose File    css:input[type="file"]    ${sample_file}
    Wait Until Page Contains    Packaging Data    40s
    Page Should Contain    12 lignes
    Page Should Contain    10 colonnes
    Page Should Contain    Valeurs manquantes

03 - Auditer la qualité des données
    Click Link    Qualité des données
    Wait Until Location Is    ${FRONTEND_URL}/data-quality    20s
    Wait Until Page Contains    Qualité par colonne    30s
    Page Should Contain    component_id
    Page Should Contain    supplier
    Page Should Contain    missing_values
    Page Should Contain    2 valeur(s) manquante(s)

04 - Configurer le dashboard métier
    Click Link    Tableau de bord
    Wait Until Location Is    ${FRONTEND_URL}/dashboard    20s
    Wait Until Page Contains    Configuration    30s
    Wait Until Element Is Enabled    css:select[aria-label="Dimension"]    30s
    Select From List By Value    css:select[aria-label="Dimension"]    supplier
    Wait Until Page Contains    par supplier    30s
    Wait Until Element Is Enabled    css:select[aria-label="Mesure"]    30s
    Select From List By Value    css:select[aria-label="Mesure"]    recyclability_score
    Wait Until Element Is Enabled    css:select[aria-label="Agrégation"]    30s
    Select From List By Value    css:select[aria-label="Agrégation"]    mean
    Wait Until Page Contains    mean de recyclability_score par supplier    30s

05 - Exécuter IsolationForest
    Click Link    Anomalies
    Wait Until Location Is    ${FRONTEND_URL}/anomalies    20s
    Wait Until Page Contains    Anomalies détectées    30s
    Page Should Contain    Lignes signalées

06 - Utiliser le fallback de l'assistant IA
    Click Link    Assistant IA
    Wait Until Location Is    ${FRONTEND_URL}/ai-assistant    20s
    Wait Until Element Is Enabled    xpath=//button[normalize-space()="Générer"]    30s
    Click Button    xpath=//button[normalize-space()="Générer"]
    Wait Until Page Contains    Fallback local    40s
    Input Text    css:textarea    Combien de valeurs manquantes ?
    Press Keys    css:textarea    RETURN
    Wait Until Element Contains    xpath=(//*[@data-testid="assistant-message"])[last()]    2 valeur(s) manquante(s)    40s

07 - Générer un rapport HTML réel
    Click Link    Rapports
    Wait Until Location Is    ${FRONTEND_URL}/reports    20s
    Wait Until Element Is Enabled    xpath=//button[normalize-space()="HTML"]    30s
    Click Button    xpath=//button[normalize-space()="HTML"]
    Wait Until Page Contains    Télécharger    40s
    Element Should Contain    css:[data-testid="report-content"]    Packaging Data
    Page Should Contain    contenu produit par FastAPI

08 - Retrouver l'analyse dans SQLite
    Click Link    Historique
    Wait Until Location Is    ${FRONTEND_URL}/history    20s
    Wait Until Element Is Visible    xpath=//tr[td[normalize-space()="report_generated"]]    40s
    Element Should Contain    xpath=//tr[td[normalize-space()="report_generated"]]    Packaging Data
    Element Should Contain    xpath=//tr[td[normalize-space()="report_generated"]]    completed
    Element Should Contain    xpath=//tr[td[normalize-space()="report_generated"]]    format: html

09 - Rejeter un XLSX invalide sans perdre le dataset actif
    [Documentation]    Vérifie l'erreur utilisateur et l'atomicité de l'import.
    Go To    ${FRONTEND_URL}
    Wait Until Page Contains    Packaging Data    30s
    ${broken_xlsx}=    Normalize Path    ${BROKEN_XLSX}
    Choose File    css:input[type="file"]    ${broken_xlsx}
    Wait Until Element Contains    css:[role="alert"]    n'est pas une archive Excel valide    30s
    Page Should Contain    Packaging Data
    Page Should Contain    12 lignes
    Click Button    xpath=//*[@role="alert"]//button[normalize-space()="Fermer"]

10 - Afficher une détection non applicable sans faux résultat
    [Documentation]    Un dataset sans variable numérique ne doit pas annoncer zéro anomalie détectée.
    ${non_numeric}=    Normalize Path    ${NON_NUMERIC_FILE}
    Choose File    css:input[type="file"]    ${non_numeric}
    Wait Until Page Contains    Non Numeric    40s
    Page Should Contain    6 lignes
    Click Link    Anomalies
    Wait Until Location Is    ${FRONTEND_URL}/anomalies    20s
    Wait Until Page Contains    Détection non applicable    30s
    Page Should Contain    Au moins 5 lignes et une variable numérique non constante sont nécessaires.
    Page Should Not Contain    Le modèle n’a signalé aucune ligne atypique.

11 - Visualiser un dataset entièrement numérique
    [Documentation]    Vérifie le choix automatique d'une dimension et d'une métrique distinctes.
    ${numeric_only}=    Normalize Path    ${NUMERIC_ONLY_FILE}
    Choose File    css:input[type="file"]    ${numeric_only}
    Wait Until Page Contains    Numeric Only    40s
    Click Link    Tableau de bord
    Wait Until Location Is    ${FRONTEND_URL}/dashboard    20s
    Wait Until Element Is Enabled    css:select[aria-label="Dimension"]    30s
    List Selection Should Be    css:select[aria-label="Dimension"]    x
    List Selection Should Be    css:select[aria-label="Mesure"]    y
    Wait Until Page Contains    sum de y par x    30s

12 - Fermer puis rouvrir une session
    [Documentation]    Vérifie que la déconnexion invalide le cookie avant de poursuivre la suite.
    Click Button    css:button[aria-label="Se déconnecter"]
    Wait Until Location Is    ${FRONTEND_URL}/login    20s
    Go To    ${FRONTEND_URL}/
    Wait Until Location Contains    /login    20s
    Input Password    css:input[name="password"]    ${ACCESS_PASSWORD}
    Click Button    xpath=//button[normalize-space()="Accéder au workspace"]
    Wait Until Location Is    ${FRONTEND_URL}/    20s
    Wait Until Page Contains    Score qualité    30s

13 - Signaler clairement une API indisponible
    [Documentation]    Coupe uniquement le backend Robot puis vérifie l'état d'erreur du frontend.
    Terminate Process    robot-backend    kill=True
    Reload Page
    Wait Until Page Contains    Chargement impossible    30s
    Page Should Contain    Le service d'analyse est temporairement indisponible
    Page Should Contain    Réessayer


*** Keywords ***
Démarrer la stack Robot
    Create Directory    ${RESULTS_DIR}
    Run Keyword And Ignore Error    Remove Directory    ${RUNTIME_DIR}    recursive=True
    Directory Should Not Exist    ${RUNTIME_DIR}
    Create Directory    ${RUNTIME_DIR}
    # Next.js recalcule ces deux fichiers selon NEXT_DIST_DIR au démarrage.
    # Une copie exacte permet au teardown de préserver le workspace du développeur.
    Copy File    ${FRONTEND_DIR}${/}next-env.d.ts    ${RUNTIME_DIR}${/}next-env.d.ts
    Copy File    ${FRONTEND_DIR}${/}tsconfig.json    ${RUNTIME_DIR}${/}tsconfig.json
    Start Process
    ...    ${PYTHON_COMMAND}
    ...    -m
    ...    uvicorn
    ...    backend.main:app
    ...    --host
    ...    127.0.0.1
    ...    --port
    ...    8100
    ...    cwd=${PROJECT_ROOT}
    ...    alias=robot-backend
    ...    stdout=${RESULTS_DIR}${/}backend.log
    ...    stderr=STDOUT
    ...    env:FRONTEND_ORIGINS=${FRONTEND_URL}
    ...    env:COPILOT_ENVIRONMENT=production
    ...    env:BACKEND_SERVICE_TOKEN=${SERVICE_TOKEN}
    ...    env:API_DOCS_ENABLED=false
    ...    env:OPENAI_API_KEY=${EMPTY}
    ...    env:COPILOT_UPLOADS_DIR=${RUNTIME_DIR}${/}uploads
    ...    env:COPILOT_REPORTS_DIR=${RUNTIME_DIR}${/}reports
    ...    env:COPILOT_DATABASE_PATH=${RUNTIME_DIR}${/}history.db
    Start Process
    ...    ${NODE_COMMAND}
    ...    ${ROBOT_SERVER}
    ...    cwd=${FRONTEND_DIR}
    ...    alias=robot-frontend
    ...    stdout=${RESULTS_DIR}${/}frontend.log
    ...    stderr=STDOUT
    ...    env:BACKEND_INTERNAL_URL=${API_URL}
    ...    env:BACKEND_SERVICE_TOKEN=${SERVICE_TOKEN}
    ...    env:DEMO_ACCESS_PASSWORD=${ACCESS_PASSWORD}
    ...    env:SESSION_SECRET=${SESSION_SECRET}
    ...    env:NEXT_DIST_DIR=.next-robot
    ...    env:NODE_ENV=development
    ...    env:NEXT_TELEMETRY_DISABLED=1
    ...    env:ROBOT_FRONTEND_HOST=127.0.0.1
    ...    env:ROBOT_FRONTEND_PORT=3100
    Wait Until Keyword Succeeds    120s    1s    L'API doit répondre
    Wait Until Keyword Succeeds    120s    1s    Le frontend doit répondre
    ${options}=    Evaluate    selenium.webdriver.ChromeOptions()    modules=selenium.webdriver
    Call Method    ${options}    add_argument    --headless\=new
    Call Method    ${options}    add_argument    --window-size\=1440,1000
    Call Method    ${options}    add_argument    --no-sandbox
    Open Browser    ${FRONTEND_URL}    Chrome    options=${options}
    Set Selenium Speed    0.15s

L'API doit répondre
    ${status}=    Evaluate    __import__('urllib.request', fromlist=['urlopen']).urlopen('${API_URL}/api/health', timeout=2).status
    Should Be Equal As Integers    ${status}    200

Le frontend doit répondre
    ${status}=    Evaluate    __import__('urllib.request', fromlist=['urlopen']).urlopen('${FRONTEND_URL}', timeout=2).status
    Should Be Equal As Integers    ${status}    200

Arrêter la stack Robot
    Run Keyword And Ignore Error    Close All Browsers
    Run Keyword And Ignore Error    Terminate Process    robot-frontend    kill=True
    Run Keyword And Ignore Error    Terminate Process    robot-backend    kill=True
    Run Keyword And Ignore Error    Copy File    ${RUNTIME_DIR}${/}next-env.d.ts    ${FRONTEND_DIR}${/}next-env.d.ts
    Run Keyword And Ignore Error    Copy File    ${RUNTIME_DIR}${/}tsconfig.json    ${FRONTEND_DIR}${/}tsconfig.json
