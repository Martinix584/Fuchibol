{{ config(
    partition_by={'field': 'transfer_date', 'data_type': 'date', 'granularity': 'year'},
    cluster_by=['to_league_id', 'to_club_id']
) }}

{#
  ¿Valió lo que se pagó? Solo fichajes con monto pagado (> 0).

  Veredicto (umbrales simples y explícitos, a propósito):
    Acierto   -> 1 año después vale >= 1.2x lo que se pagó y jugó >= 50% de los minutos
    Fracaso   -> vale < 0.6x lo pagado, o jugó < 25% de los minutos
    Cumplió   -> el resto
    Muy reciente -> todavía no pasó un año desde el fichaje
#}
with transfers as (

    select
        *,
        round(safe_divide(value_1y_after_eur, transfer_fee_eur), 3) as value_to_fee_ratio,
        round(safe_divide(value_1y_after_eur - market_value_at_transfer_eur, market_value_at_transfer_eur), 3)
            as value_change_pct,
        round(safe_divide(transfer_fee_eur, market_value_at_transfer_eur), 3) as fee_to_market_value_ratio
    from {{ ref('int_transfers_enriched') }}
    where is_paid_transfer

)

select
    *,
    case
        when not has_full_window then 'Muy reciente'
        when value_to_fee_ratio is null then 'Sin datos'
        when value_to_fee_ratio >= 1.2 and minutes_share_after >= 0.5 then 'Acierto'
        when value_to_fee_ratio < 0.6 or coalesce(minutes_share_after, 0) < 0.25 then 'Fracaso'
        else 'Cumplió'
    end as verdict

from transfers
