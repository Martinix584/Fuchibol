{# Balance de cada club en el mercado: gasto, ingresos y tasa de aciertos de sus compras. #}
with purchases as (

    select
        to_club_id as club_id,
        count(*) as signings,
        sum(transfer_fee_eur) as spent_eur,
        avg(value_to_fee_ratio) as avg_value_to_fee_ratio,
        countif(verdict = 'Acierto') as hits,
        countif(verdict = 'Fracaso') as flops,
        countif(verdict in ('Acierto', 'Cumplió', 'Fracaso')) as evaluated_signings
    from {{ ref('mart_transfer_roi') }}
    group by to_club_id

),

sales as (

    select
        from_club_id as club_id,
        count(*) as sales,
        sum(transfer_fee_eur) as income_eur
    from {{ ref('mart_transfer_roi') }}
    group by from_club_id

)

select
    clubs.club_id,
    clubs.club_name,
    clubs.league_name,
    clubs.league_country,
    coalesce(purchases.signings, 0) as signings,
    coalesce(purchases.spent_eur, 0) as spent_eur,
    coalesce(sales.sales, 0) as sales,
    coalesce(sales.income_eur, 0) as income_eur,
    coalesce(sales.income_eur, 0) - coalesce(purchases.spent_eur, 0) as net_balance_eur,
    round(purchases.avg_value_to_fee_ratio, 3) as avg_value_to_fee_ratio,
    purchases.evaluated_signings,
    round(safe_divide(purchases.hits, purchases.evaluated_signings), 3) as hit_rate,
    round(safe_divide(purchases.flops, purchases.evaluated_signings), 3) as flop_rate

from {{ ref('dim_clubs') }} as clubs
left join purchases using (club_id)
left join sales using (club_id)
where purchases.club_id is not null or sales.club_id is not null
