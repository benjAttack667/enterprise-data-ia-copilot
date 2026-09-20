*** Settings ***
Documentation     Parcours navigateur court contre le bundle Docker/standalone de production.
...               La stack doit déjà répondre sur les URLs configurées. Aucun serveur de
...               développement Next.js n'est démarré par cette suite.
Library           Collections
Library           OperatingSystem
Library           SeleniumLibrary    timeout=25s
Suite Setup       Ouvrir le frontend de production
Suite Teardown    Fermer le frontend et vérifier la console
Test Tags         e2e    production    robot-framework


*** Variables ***
${FRONTEND_URL}       %{PRODUCTION_FRONTEND_URL=http://localhost:3000}
${ACCESS_PASSWORD}    %{DEMO_ACCESS_PASSWORD}
${PROJECT_ROOT}       ${CURDIR}${/}..${/}..
${SAMPLE_FILE}        ${PROJECT_ROOT}${/}backend${/}data${/}samples${/}packaging_data.csv
${RESULTS_DIR}        ${CURDIR}${/}results${/}production


*** Test Cases ***
00 - Ouvrir une session sur le bundle standalone
    Wait Until Location Contains    /login    20s
    Page Should Contain    Connexion au workspace
    Input Password    css:input[name="password"]    ${ACCESS_PASSWORD}
    Click Button    xpath=//button[normalize-space()="Accéder au workspace"]
    Wait Until Location Is    ${FRONTEND_URL}/    20s
    Wait Until Page Contains    Marketing Leads    30s
    Page Should Contain    15 lignes
    Page Should Contain    11 colonnes

01 - Importer un CSV via les conteneurs de production
    ${sample_file}=    Normalize Path    ${SAMPLE_FILE}
    File Should Exist    ${sample_file}
    Choose File    css:input[type="file"]    ${sample_file}
    Wait Until Page Contains    Packaging Data    40s
    Page Should Contain    12 lignes
    Page Should Contain    10 colonnes

02 - Naviguer et recharger le dashboard de production
    Click Link    Qualité des données
    Wait Until Location Is    ${FRONTEND_URL}/data-quality    20s
    Wait Until Page Contains    Qualité par colonne    30s
    Page Should Contain    component_id
    Click Link    Tableau de bord
    Wait Until Location Is    ${FRONTEND_URL}/dashboard    20s
    Wait Until Element Is Enabled    css:select[aria-label="Dimension"]    30s
    Select From List By Value    css:select[aria-label="Dimension"]    supplier
    Select From List By Value    css:select[aria-label="Mesure"]    recyclability_score
    Select From List By Value    css:select[aria-label="Agrégation"]    mean
    Wait Until Page Contains    mean de recyclability_score par supplier    30s
    Capture Page Screenshot    production-dashboard.png
    Reload Page
    Wait Until Page Contains    Packaging Data    30s
    Wait Until Page Contains    Configuration    30s
    Go Back
    Wait Until Location Is    ${FRONTEND_URL}/data-quality    20s
    Execute Javascript    window.history.forward()
    Wait Until Location Is    ${FRONTEND_URL}/dashboard    20s
    Wait Until Page Contains    Configuration    30s

03 - Invalider la session de production
    Click Button    css:button[aria-label="Se déconnecter"]
    Wait Until Location Is    ${FRONTEND_URL}/login    20s
    Go To    ${FRONTEND_URL}/dashboard
    Wait Until Location Contains    /login    20s
    Page Should Contain    Connexion au workspace


*** Keywords ***
Ouvrir le frontend de production
    Create Directory    ${RESULTS_DIR}
    ${options}=    Evaluate    selenium.webdriver.ChromeOptions()    modules=selenium.webdriver
    Call Method    ${options}    add_argument    --headless\=new
    Call Method    ${options}    add_argument    --window-size\=1440,1000
    Call Method    ${options}    add_argument    --no-sandbox
    ${logging_preferences}=    Create Dictionary    browser=ALL
    Call Method    ${options}    set_capability    goog:loggingPrefs    ${logging_preferences}
    Open Browser    ${FRONTEND_URL}    Chrome    options=${options}
    Set Selenium Speed    0.10s

Lire la console du navigateur
    ${selenium}=    Get Library Instance    SeleniumLibrary
    ${driver}=    Set Variable    ${selenium.driver}
    ${entries}=    Call Method    ${driver}    get_log    browser
    RETURN    ${entries}

Fermer le frontend et vérifier la console
    ${console_status}    ${console_entries}=    Run Keyword And Ignore Error    Lire la console du navigateur
    Run Keyword And Ignore Error    Close All Browsers
    IF    '${console_status}' == 'FAIL'
        Fail    Impossible de lire la console Chrome : ${console_entries}
    END
    Log Many    @{console_entries}
    ${unexpected}=    Evaluate
    ...    [entry for entry in $console_entries if entry.get("level") == "SEVERE" or any(marker in entry.get("message", "").lower() for marker in ("hydration", "uncaught", "minified react error"))]
    Should Be Empty    ${unexpected}    msg=La console du bundle de production contient une erreur inattendue : ${unexpected}
