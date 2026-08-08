# Certificats réseau optionnels

Sur un réseau d'entreprise qui inspecte TLS, placez ici chaque autorité racine
interne au format PEM, avec l'extension `.crt`, puis reconstruisez les images.
Ces certificats sont ajoutés aux magasins Linux de Python et Node pendant le
build. Les fichiers `.crt` restent ignorés par Git et ne doivent jamais contenir
de clé privée.

Sur un réseau public classique, ce dossier peut rester sans fichier `.crt`.
