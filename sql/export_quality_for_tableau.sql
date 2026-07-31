-- Export: one row per hospital, with overall star rating plus the
-- safety and readmission "better than national average" component
-- counts. Designed to join against export_prices_for_tableau.csv on
-- hospital_name inside Tableau.
--
-- CHOA will show NULL for overall_rating (CMS excludes pediatric
-- hospitals from standard quality reporting -- confirmed directly in
-- this data, see data/README.md).

SELECT
    h.hospital_name,
    MAX(CASE WHEN qm.measure_name='Hospital overall rating' THEN qm.measure_value END) AS overall_rating,
    MAX(CASE WHEN qm.measure_name='Count of Safety Measures Better' THEN qm.measure_value END) AS safety_measures_better,
    MAX(CASE WHEN qm.measure_name='Count of Facility Safety Measures' THEN qm.measure_value END) AS safety_measures_total,
    MAX(CASE WHEN qm.measure_name='Count of READM Measures Better' THEN qm.measure_value END) AS readm_measures_better,
    MAX(CASE WHEN qm.measure_name='Count of Facility READM Measures' THEN qm.measure_value END) AS readm_measures_total,
    CASE
        WHEN h.hospital_name IN ('Emory University Hospital', 'Wellstar Kennestone Hospital')
            THEN 'low_confidence'
        WHEN h.hospital_name = 'Arthur M. Blank Hospital'
            THEN 'no_rating_pediatric'
        ELSE 'reliable'
    END AS reliability_flag
FROM hospitals h
LEFT JOIN quality_measures qm ON qm.hospital_id = h.hospital_id
GROUP BY h.hospital_name
ORDER BY overall_rating DESC;