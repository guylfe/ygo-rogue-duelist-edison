"""Shared unlock observations; reads results without modifying duel gameplay."""
from collections import Counter
import duel_rewards
from content import PROGRESSION

LATER_ROSTERS = PROGRESSION['campaign_roster']
STARTERS = {0, 1} | {i for roster in LATER_ROSTERS.values() for i in roster['starters']}
LATER_UNLOCKS = {int(i) for roster in LATER_ROSTERS.values() for i in roster['unlocks']}
ROSTER_ACT = {int(i): int(act) for act, roster in LATER_ROSTERS.items() for i in (*roster['starters'], *roster['unlocks'])}
SPECIAL = {37, 38}  # Copycat and Dueling Engine
CUMULATIVE = {'victories', 'duel_coins', 'boss_wins', 'singles_bought', 'dice_and_coins'}
VERSION = 1


def rule(character):
 act = ROSTER_ACT.get(character, 1)
 if character in STARTERS:
  return act, 'wins', 0, 'Available from the beginning'
 rules = LATER_ROSTERS[str(act)]['unlocks'] if act > 1 else PROGRESSION['unlocks']
 row = rules[str(character)]
 description = row['description']
 if act == 1 and character not in SPECIAL:
  description = description.replace('Win a run with ', 'Clear Act I with ').replace('Beat a run without', 'Clear Act I without')
 return act, row['metric'], row['target'], description


def value(profile, character):
 act, metric, _, _ = rule(character)
 def amount(stats):
  if metric.startswith('won_as:'):
   return int(int(metric.split(':')[1]) in stats.get('won_as', []))
  return stats.get(metric, 0)
 if character in SPECIAL:
  return amount(profile)
 progress = profile.get('campaign_unlock_progress', {})
 result = amount(progress.get(str(act), {}))
 return max(result, amount(progress.get('legacy', {}))) if act == 1 else result


def migrate(profile, runs=()):
 """Keep later-series access where the old save shows actual use or an explicit grant."""
 unlocked = set(profile.get('unlocked', []))
 if profile.get('campaign_roster_version', 0) < VERSION:
  used = {row.get('character') for row in [*profile.get('run_history', []), *runs] if isinstance(row, dict)}
  used.update(profile.get('won_as', []))
  used.update(i for i in LATER_UNLOCKS if profile.get('character_levels', {}).get(str(i), -1) >= 0)
  synced = profile.get('synced_achievements')
  if isinstance(synced, list):
   used.update(i for i in LATER_UNLOCKS if f'character:{i}' in synced)
  if not profile.get('unlock_all') and not profile.get('testing_all_clears'):
   unlocked -= LATER_UNLOCKS - used
  unlocked |= used & LATER_UNLOCKS
  profile['campaign_roster_version'] = VERSION
 profile['unlocked'] = sorted(unlocked | STARTERS)


def observe_unlocks(profile, run, won, duel_progress):
 """Track ordinary character milestones in the encounter's Act, including its final duel."""
 import campaign_acts as acts
 act = run.get('act')
 if run.get('secret_challenge') or (act and (run.get('loop') or run.get('encore_active') or run.get('encore_won'))):
  return None
 scope = str(act) if act else 'legacy'
 progress = profile.setdefault('campaign_unlock_progress', {}).setdefault(scope, {})
 # Keep a credit watermark per save slot. A retried save can have the same duel result or purchase count.
 slot = 'tag' if run.get('history_mode') == 'tag' else str(run.get('_save_slot', 1))
 ident = [run.get('started_at'), run['character']]
 credits = profile.setdefault('campaign_unlock_credits', {})
 credit = credits.get(slot, {})
 if credit.get('run') != ident:
  credit = {'run': ident, 'singles': run.get('credited_singles', 0)}
  credits[slot] = credit
 bought = run.get('singles_bought', 0)
 delta = max(0, bought - credit['singles'])
 if delta:
  progress['singles_bought'] = progress.get('singles_bought', 0) + delta
  credit['singles'] = bought
 if scope in ('1', 'legacy'):
  progress['max_gold'] = max(progress.get('max_gold', 0), run['gold'])
  progress['relic_variety'] = max(progress.get('relic_variety', 0), len(set(run['artifacts'])))
  # These legacy run flags are unambiguous before the first transition and in noncampaign runs.
  progress.update(dict.fromkeys(run.get('character_challenges', []), 1))
 if duel_progress and credit.get('duel') != run['duel']['id']:
  feats, boss, dice, coins = duel_progress
  credit['duel'] = run['duel']['id']
  progress.update(dict.fromkeys(feats, 1))
  for key, count in (('dice_rolled', dice), ('coins_tossed', coins)):
   progress[key] = progress.get(key, 0) + count
  progress['dice_and_coins'] = min(progress['dice_rolled'], progress['coins_tossed'])
  if won:
   progress['victories'] = progress.get('victories', 0) + 1
   progress['boss_wins'] = progress.get('boss_wins', 0) + int(boss)
   progress['duel_coins'] = progress.get('duel_coins', 0) + run.get('last_gold', 0)
 clear = (run['stage'] == 'complete' if act is None else
          won and run['stage'] in ('act_transition', 'complete') and run['round'] == acts.ACTS[act-1]['duels'])
 if clear:
  progress['act_clear'] = 1
  progress['challenge_clear'] = max(progress.get('challenge_clear', 0), run.get('challenge_level', 0))
  progress['won_as'] = sorted(set(progress.get('won_as', [])) | {run['character']})
  if not run.get('relics_bought', 0):
   progress['relicless_shop'] = 1
 return act or 1

def observe(profile,run):
 profile['packs_variety']=max(profile.get('packs_variety',0),len(set(run.get('bought_pack_ids',[]))))
 profile['relic_variety']=max(profile.get('relic_variety',0),len(set(run.get('artifacts',[]))))
 # Per-run watermark makes repeated saves/profile refreshes idempotent.
 purchased=run.get('singles_bought',0)
 profile['singles_bought']=profile.get('singles_bought',0)+max(0,purchased-run.get('credited_singles',0))
 run['credited_singles']=purchased
 for key in run.get('character_challenges',[]):profile[key]=1
 if run.get('secret_challenge') and run.get('encore_won'):
  profile['relicless_unlocked' if run.get('secret_challenge')=='relicless' else 'gallery_unlocked']=True
 if not run.get('secret_challenge') and run.get('stage')=='complete' and not run.get('card_purchases',run.get('purchased',0)):
  profile['frugal_run']=1
 if not run.get('secret_challenge') and run.get('stage')=='complete' and not run.get('relics_bought',0):
  profile['relicless_shop']=1
 import sleeve_progress
 sleeve_progress.observe(profile,run)
 # Duke Devlin unlock (2026-11-13): roll 10 dice and toss 10 coins across all duels; progress shows the smaller count.
 stats=profile.get('sleeve_stats',{})
 profile['dice_and_coins']=min(int(stats.get('diceRolled',0)),int(stats.get('coinsTossed',0)))

def duel(game,run,result,won,boss):
 cards=[game.BY_ID[c] for c in game.deck(run) if not game.is_extra(c)]
 metrics=duel_rewards.metrics(run,result.get('events',[]),game.BY_ID)
 conditions={
  'six_attributes':{'LIGHT','DARK','FIRE','WATER','WIND','EARTH'}<=set(c.get('attribute') for c in cards if c['data']['type']&1),
  'tribute_roster':sum(c.get('level',0)>=5 and bool(c['data']['type']&1) for c in cards)>=6,
  'ten_thousand_lp':result['lp']>=10000,
  'singleton_win':bool(cards) and len({game.limit_identity(c['id']) if run.get('act')==3 else c['id'] for c in cards})==len(cards),
  'clutch_boss':boss and 0<result['lp']<=500,
  'two_rituals':metrics['ritual']>=2,
  'five_banished':any(e.get('kind')=='duel_metrics' and e.get('banished_count',0)>=5 for e in result.get('events',[])),
  'fusion_win':metrics['fusion']>0,
  'sixty_win':len(cards)==60,
  'normal_win':bool(cards) and all(c['data']['type']&1 for c in cards),
  'champion_win':bool(run.get('encore_active')),
 }
 import sleeve_progress
 # Who was beaten, for the 'Defeat <duelist> 5 times' sleeves (2026-11-20); the loop challenge is the World Champion
 # on loop 0 and Obelisk after that.
 if run.get('encore_active') and not run.get('secret_challenge'):opponent='World Champion' if not run.get('encore_opponent') else 'Obelisk the Tormenter'
 else:
  index=(run.get('duel') or {}).get('opponent',run.get('opponent'))
  opponent=game.CHARACTERS[index]['name'] if isinstance(index,int) and 0<=index<len(game.CHARACTERS) else None
 sleeve_progress.duel(run,result,won,metrics,cards=cards,boss=boss,opponent=opponent)
 feats={k for k,v in conditions.items() if v and (won or k=='two_rituals')}
 run['character_challenges']=sorted(set(run.get('character_challenges',[]))|feats)
 telemetry=next((event for event in result.get('events',[]) if event.get('kind')=='sleeve_metrics'),{})
 if won and run.get('act') == 2:
  feats.update(key for key, met in {
   'burn_win': metrics['effect_damage'] >= 1500,
   'equip_win': metrics['equip'] >= 2,
   'big_summons_win': metrics['high_level'] >= 3,
   'special_summons_win': metrics['special_summons'] >= 3,
   'monster_types_win': len({c['race'] for c in cards if c['data']['type'] & 1}) >= 4,
   'forty_cards_win': len(cards) >= 40,
   'low_lp_boss': boss and 0 < result['lp'] <= 3000,
   'battle_destroy_win': metrics['battle_destroy'] >= 3,
   'attacks_win': metrics['attacks'] >= 4,
   'long_win': metrics['turns'] - int(run.get('first_player') == 1) >= 12,
  }.items() if met)
 if won and run.get('act') == 3:
  feats.update(key for key, met in {
   'synchro_win': metrics['synchro'] > 0,
   'trap_win': metrics['traps'] >= 2,
   'normal_summons_boss': boss and metrics['normal_summons'] >= 3,
   'battle_damage_win': metrics['damage'] - metrics['effect_damage'] >= 5000,
   'recover_win': metrics['recover'] >= 1500,
   'grave_summon_win': telemetry.get('graveSpecials',0) >= 1,
   'monster_effects_win': metrics['effects'] >= 3,
   'quick_win': metrics['early_ten'],
  }.items() if met)
 return feats,boss,max(0,int(telemetry.get('diceRolled',0) or 0)),max(0,int(telemetry.get('coinsTossed',0) or 0))
