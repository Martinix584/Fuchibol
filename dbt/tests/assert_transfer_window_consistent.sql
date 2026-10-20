{{ config(severity='warn') }}
-- Un jugador no puede jugar más minutos en el club nuevo que los que jugó el club (+5% de margen por alargues).
select transfer_id, minutes_after, club_games_after
from {{ ref('int_transfers_enriched') }}
where minutes_after > club_games_after * 90 * 1.05
