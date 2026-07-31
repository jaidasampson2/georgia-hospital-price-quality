-- Export: one row per price observation, labeled and flagged for
-- direct use in Tableau. Deliberately NOT pre-aggregated (no AVG/MEDIAN
-- here) -- Tableau does its own grouping, filtering, and summary
-- statistics far better than a pre-computed SQL result would let it.
--
-- Excludes billing_class = 'professional' (Grady's physician-fee rows)
-- throughout, consistent with every other query in this project.
--
-- reliability_flag: 'low_confidence' marks Emory and Wellstar, whose
-- price samples were shown to skew toward Medicare Advantage payers
-- (see data/README.md, Finding 5). Everything else is 'reliable'.
-- Build this into a filter or color encoding in Tableau rather than
-- silently including or excluding these rows.

SELECT
    h.hospital_name,
    h.source_format,
    CASE
        WHEN s.cpt_code = '70450' OR s.hcpcs_code = '70450' THEN 'Head CT'
        WHEN s.cpt_code = '73721' OR s.hcpcs_code = '73721' THEN 'Knee MRI'
        WHEN s.cpt_code IN ('45378','45380') OR s.hcpcs_code IN ('45378','45380') THEN 'Colonoscopy'
        WHEN s.cpt_code = '93017' OR s.hcpcs_code = '93017' THEN 'Cardiac Stress Test'
    END AS procedure,
    s.description,
    s.billing_class,
    s.modifiers,
    p.setting,
    p.payer_name,
    p.plan_name,
    p.gross_charge,
    p.price_type,
    p.resolved_price,
    CASE
        WHEN h.hospital_name IN ('Emory University Hospital', 'Wellstar Kennestone Hospital')
            THEN 'low_confidence'
        ELSE 'reliable'
    END AS reliability_flag
FROM prices p
JOIN services s ON p.service_id = s.service_id
JOIN hospitals h ON s.hospital_id = h.hospital_id
WHERE (s.cpt_code IN ('70450','73721','45378','45380','93017')
    OR s.hcpcs_code IN ('70450','73721','45378','45380','93017'))
  AND s.billing_class != 'professional'
ORDER BY procedure, h.hospital_name;