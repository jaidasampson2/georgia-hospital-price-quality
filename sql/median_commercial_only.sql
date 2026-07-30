WITH labeled AS (
  SELECT
    h.hospital_name AS hospital_name,
    CASE
      WHEN s.cpt_code = '70450' OR s.hcpcs_code = '70450' THEN 'Head CT'
      WHEN s.cpt_code = '73721' OR s.hcpcs_code = '73721' THEN 'Knee MRI'
      WHEN s.cpt_code IN ('45378','45380') OR s.hcpcs_code IN ('45378','45380') THEN 'Colonoscopy'
      WHEN s.cpt_code = '93017' OR s.hcpcs_code = '93017' THEN 'Cardiac Stress Test'
    END AS procedure,
    p.resolved_price AS price
  FROM prices p
  JOIN services s ON p.service_id = s.service_id
  JOIN hospitals h ON s.hospital_id = h.hospital_id
  WHERE (s.cpt_code IN ('70450','73721','45378','45380','93017')
      OR s.hcpcs_code IN ('70450','73721','45378','45380','93017'))
    AND s.billing_class != 'professional'
    AND p.resolved_price IS NOT NULL
    AND LOWER(p.payer_name) NOT LIKE '%medicare%'
    AND LOWER(p.plan_name) NOT LIKE '%medicare%'
),
ranked AS (
  SELECT hospital_name, procedure, price,
    ROW_NUMBER() OVER (PARTITION BY hospital_name, procedure ORDER BY price) AS rn,
    COUNT(*) OVER (PARTITION BY hospital_name, procedure) AS cnt
  FROM labeled
)
SELECT hospital_name, procedure, ROUND(AVG(price), 2) AS median_price, MAX(cnt) AS n_rates
FROM ranked
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
GROUP BY hospital_name, procedure
ORDER BY procedure, hospital_name;
