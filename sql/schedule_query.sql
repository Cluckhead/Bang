-- Purpose: Dummy T-SQL to be replaced by the user's real query later.
-- Expected result set columns (names can be aliased):
--   ISIN, [CRD ID], [Day Basis], [First Coupon], [Maturity Date], [Accrued Interest], [Issue Date], [Call Schedule], [Coupon Frequency]

-- Example stub: return zero rows with the correct schema using SELECT ... WHERE 1=0
SELECT
    CAST(NULL AS varchar(20)) AS ISIN,
    CAST(NULL AS int)         AS [CRD ID],
    CAST(NULL AS varchar(16)) AS [Day Basis],
    CAST(NULL AS date)        AS [First Coupon],
    CAST(NULL AS date)        AS [Maturity Date],
    CAST(NULL AS decimal(18,8)) AS [Accrued Interest],
    CAST(NULL AS date)        AS [Issue Date],
    CAST(NULL AS nvarchar(max)) AS [Call Schedule], -- JSON stringified array of call entries
    CAST(NULL AS int)         AS [Coupon Frequency]
WHERE 1 = 0;


