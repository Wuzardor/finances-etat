-- Vues analytiques consommées par le tableau de bord.
-- Tous les montants sont en euros. Convention : recettes et dépenses positives,
-- soldes négatifs en cas de déficit.

-- Exécution budgétaire mensuelle : cumul depuis le 1er janvier et flux du mois
CREATE OR REPLACE VIEW v_execution_mensuelle AS
SELECT
    s.date_arrete,
    year(s.date_arrete)  AS annee,
    month(s.date_arrete) AS mois,
    r.code,
    r.libelle_court      AS libelle,
    r.famille,
    r.parent,
    r.ordre,
    s.cumul,
    s.cumul - coalesce(
        lag(s.cumul) OVER (PARTITION BY r.code, year(s.date_arrete) ORDER BY s.date_arrete), 0
    ) AS montant_mois
FROM stg_smb s
JOIN ref_lignes r USING (code);

-- Cumul à fin de mois comparé au même mois de l'année précédente
CREATE OR REPLACE VIEW v_cumul_vs_n1 AS
SELECT
    n.*,
    p.cumul           AS cumul_n1,
    n.cumul - p.cumul AS ecart_n1
FROM v_execution_mensuelle n
LEFT JOIN v_execution_mensuelle p
    ON p.code = n.code AND p.annee = n.annee - 1 AND p.mois = n.mois;

-- Budget annuel : loi de finances initiale, dernière loi rectificative, exécution.
-- L'exécution vient du cumul de décembre des SMB, à défaut du fichier des textes
-- (qui contient des erreurs connues, voir ref/anomalies_connues.csv).
CREATE OR REPLACE VIEW v_budget_annuel AS
WITH lois AS (
    SELECT
        annee, code,
        max(montant) FILTER (WHERE texte_code = 'lfi')       AS lfi,
        max(montant) FILTER (WHERE texte_code = 'lfr')       AS derniere_lfr,
        max(montant) FILTER (WHERE texte_code = 'execution') AS execution
    FROM stg_lois
    WHERE code IS NOT NULL
    GROUP BY ALL
),
decembre AS (
    SELECT annee, code, cumul AS execution_smb
    FROM v_execution_mensuelle
    WHERE mois = 12
)
SELECT
    annee, code,
    r.libelle_court AS libelle, r.famille, r.parent, r.ordre,
    lfi, derniere_lfr,
    coalesce(execution_smb, execution) AS execution,
    execution AS execution_textes
FROM lois
FULL JOIN decembre USING (annee, code)
JOIN ref_lignes r USING (code);

-- Comptabilité générale (droits constatés). Dans la balance, les charges et
-- l'actif sont au débit (+), les produits et le passif au crédit (−).
CREATE OR REPLACE VIEW v_compte_resultat AS
SELECT
    annee,
    sum(solde) FILTER (WHERE categorie = 'Charges')                AS charges,
    -sum(solde) FILTER (WHERE categorie = 'Produits')              AS produits,
    -sum(solde) FILTER (WHERE categorie IN ('Charges', 'Produits')) AS resultat
FROM stg_compta_generale
GROUP BY annee;

CREATE OR REPLACE VIEW v_compte_resultat_postes AS
SELECT
    annee, categorie, poste, sous_poste,
    CASE WHEN categorie = 'Produits' THEN -sum(solde) ELSE sum(solde) END AS montant
FROM stg_compta_generale
WHERE categorie IN ('Charges', 'Produits')
GROUP BY annee, categorie, poste, sous_poste;

CREATE OR REPLACE VIEW v_charges_par_mission AS
SELECT
    annee,
    coalesce(mission, 'Non rattaché à une mission') AS mission,
    sum(solde) AS charges
FROM stg_compta_generale
WHERE categorie = 'Charges'
GROUP BY ALL;

CREATE OR REPLACE VIEW v_bilan AS
SELECT
    annee,
    sum(solde) FILTER (WHERE categorie = 'Actif')                              AS actif,
    -sum(solde) FILTER (WHERE categorie = 'Passif')                            AS passif,
    -sum(solde) FILTER (WHERE categorie = 'Passif' AND poste = 'Dettes financières') AS dettes_financieres,
    sum(solde) FILTER (WHERE categorie = 'Actif') + sum(solde) FILTER (WHERE categorie = 'Passif') AS situation_nette
FROM stg_compta_generale
GROUP BY annee;

CREATE OR REPLACE VIEW v_bilan_postes AS
SELECT
    annee, categorie, poste,
    CASE WHEN categorie = 'Passif' THEN -sum(solde) ELSE sum(solde) END AS montant
FROM stg_compta_generale
WHERE categorie IN ('Actif', 'Passif')
GROUP BY annee, categorie, poste;

-- Toutes administrations publiques (État, Sécurité sociale, collectivités), au sens de Maastricht
CREATE OR REPLACE VIEW v_maastricht AS
SELECT
    annee,
    max(valeur) FILTER (WHERE na_item = 'B9' AND unit = 'PC_GDP')        AS solde_pct_pib,
    max(valeur) FILTER (WHERE na_item = 'GD' AND unit = 'PC_GDP')        AS dette_pct_pib,
    max(valeur) FILTER (WHERE na_item = 'B9' AND unit = 'MIO_EUR') * 1e6 AS solde,
    max(valeur) FILTER (WHERE na_item = 'GD' AND unit = 'MIO_EUR') * 1e6 AS dette
FROM stg_eurostat
GROUP BY annee;

-- Prélèvements obligatoires par administration bénéficiaire (comptabilité nationale).
-- Catégories exclusives : leur somme égale le total des impôts et cotisations
-- sociales effectives obligatoires, avant déduction des montants non recouvrables.
CREATE OR REPLACE VIEW v_prelevements AS
WITH p AS (
    SELECT
        annee, sector,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D211'), 0)  AS d211,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D21'), 0)   AS d21,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D214'), 0)  AS d214,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D214A'), 0) AS d214a,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D29'), 0)   AS d29,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D29A'), 0)  AS d29a,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D51A'), 0)  AS d51a,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D51B'), 0)  AS d51b,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D59'), 0)   AS d59,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D91'), 0)   AS d91,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D611C'), 0) AS d611c,
        coalesce(sum(valeur) FILTER (WHERE na_item = 'D613C'), 0) AS d613c
    FROM stg_eurostat_impots
    WHERE sector <> 'S13'
    GROUP BY annee, sector
),
categories AS (
    UNPIVOT (
        SELECT
            annee, sector,
            d211                  AS "TVA",
            d51a                  AS "Impôts sur le revenu des ménages (IR, CSG, CRDS)",
            d611c + d613c         AS "Cotisations sociales",
            d51b                  AS "Impôt sur les sociétés",
            d214a                 AS "Accises (énergie, tabac, alcool…)",
            d214 - d214a          AS "Autres impôts sur les produits (droits de mutation, assurances…)",
            d29a                  AS "Impôts sur les terrains et bâtiments (taxes foncières…)",
            d29 - d29a            AS "Autres impôts sur la production (dont taxes sur les salaires)",
            d59 + d91             AS "Successions et autres impôts sur le patrimoine",
            d21 - d211 - d214     AS "Droits de douane"
        FROM p
    ) ON COLUMNS(* EXCLUDE (annee, sector)) INTO NAME prelevement VALUE mio
)
SELECT
    c.annee, c.prelevement, a.administration, a.ordre AS ordre_administration,
    c.mio * 1e6 AS montant
FROM categories c
JOIN ref_administrations a USING (sector)
WHERE abs(c.mio) > 0.05;

-- Dépenses de chaque administration par fonction (non consolidées : les transferts
-- entre administrations figurent chez celle qui les verse, en services généraux).
CREATE OR REPLACE VIEW v_depenses_fonction AS
SELECT
    d.annee, a.administration, a.ordre AS ordre_administration,
    f.fonction, f.precision, f.ordre AS ordre_fonction,
    d.valeur * 1e6 AS montant,
    d.valeur / sum(d.valeur) OVER (PARTITION BY d.annee, d.sector) AS part
FROM stg_eurostat_cofog d
JOIN ref_administrations a USING (sector)
JOIN ref_fonctions f USING (cofog99);
