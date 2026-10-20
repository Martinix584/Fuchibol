{#
  transfer_fee en el origen: null = desconocido, 0 = libre o préstamo
  (Transfermarkt no distingue ambos casos en este campo).
#}
with source as (

    select
        {{ to_int("player_id") }} as player_id,
        safe_cast(transfer_date as date) as transfer_date,
        cast(transfer_season as string) as transfer_season,
        {{ to_int("from_club_id") }} as from_club_id,
        {{ to_int("to_club_id") }} as to_club_id,
        cast(from_club_name as string) as from_club_name,
        cast(to_club_name as string) as to_club_name,
        safe_cast(transfer_fee as float64) as transfer_fee_eur,
        safe_cast(market_value_in_eur as float64) as market_value_at_transfer_eur

    from {{ source('transfermarkt', 'transfers') }}

)

select
    to_hex(md5(concat(
        cast(player_id as string), '|', cast(transfer_date as string), '|',
        coalesce(cast(from_club_id as string), ''), '|', coalesce(cast(to_club_id as string), '')
    ))) as transfer_id,
    *,
    transfer_fee_eur > 0 as is_paid_transfer

from source
where player_id is not null
    and transfer_date is not null
    and transfer_date <= current_date()  -- excluye fichajes anunciados a futuro
-- el origen puede repetir un mismo movimiento: se queda con uno
qualify row_number() over (
    partition by player_id, transfer_date, from_club_id, to_club_id
    order by transfer_fee_eur desc nulls last
) = 1
