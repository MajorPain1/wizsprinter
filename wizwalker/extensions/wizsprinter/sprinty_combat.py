import asyncio
from typing import *

import wizwalker
from wizwalker.combat import CombatHandler
from wizwalker.combat import CombatMember
from wizwalker.combat.card import CombatCard
from wizwalker.memory import EffectTarget, SpellEffects, DynamicSpellEffect
from wizwalker.memory.memory_objects.spell_effect import CompoundSpellEffect, ConditionalSpellEffect, HangingConversionSpellEffect, HangingDisposition

from .combat_backends.combat_config_parser import TargetType, TargetData, MoveConfig, TemplateSpell \
    , NamedSpell, SpellType, Spell
from .combat_backends.backend_base import BaseCombatBackend


async def get_inner_card_effects(card: CombatCard) -> List[DynamicSpellEffect]:
    effects = await card.get_spell_effects()
    output_effects: List[DynamicSpellEffect] = []

    try: 
        for effect in effects:
            effect_class = type(effect)
            if issubclass(CompoundSpellEffect, effect_class):
                output_effects += await effect.effect_list()

            elif issubclass(effect_class, ConditionalSpellEffect):
                print("This activated")
                print(type(effect))
                issubclass(effect_class, ConditionalSpellEffect)
                output_effects += [await elem.effect() for elem in await effect.elements()]

            elif issubclass(effect_class, HangingConversionSpellEffect):
                output_effects += await effect.output_effect()

            else:
                output_effects.append(effect)

    except Exception as e:
        print(e)

    return output_effects


damage_effects = {
    SpellEffects.damage,
    SpellEffects.damage_no_crit,
    SpellEffects.damage_over_time,
    SpellEffects.damage_per_total_pip_power,
    SpellEffects.instant_kill,
    SpellEffects.divide_damage,
    SpellEffects.steal_health,
    SpellEffects.max_health_damage
}

buff_damage_effects = {
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.modify_incoming_damage_over_time,
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat,
}

buff_heal_effects = {
    SpellEffects.modify_outgoing_heal,
    SpellEffects.modify_outgoing_heal_flat,
    SpellEffects.modify_incoming_heal,
    SpellEffects.modify_incoming_heal_flat,
    SpellEffects.modify_incoming_heal_over_time
}

heal_effects = {
    SpellEffects.heal,
    SpellEffects.heal_by_ward,
    SpellEffects.heal_over_time,
    SpellEffects.heal_percent,
    SpellEffects.max_health_heal
}
charm_effects = {
    SpellEffects.modify_outgoing_armor_piercing,
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat,
    SpellEffects.modify_outgoing_heal,
    SpellEffects.modify_outgoing_heal_flat,
    SpellEffects.cloaked_charm,
    SpellEffects.modify_accuracy
}
ward_effects = {
    SpellEffects.modify_incoming_armor_piercing,
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.modify_incoming_damage_over_time,
    SpellEffects.modify_incoming_heal,
    SpellEffects.modify_incoming_heal_flat,
    SpellEffects.modify_incoming_heal_over_time
}

ally_targets = {
    EffectTarget.friendly_minion,
    EffectTarget.friendly_single,
    EffectTarget.friendly_single_not_me,
    EffectTarget.friendly_team,
    EffectTarget.friendly_team_all_at_once,
    EffectTarget.multi_target_friendly,
    EffectTarget.self
}

enemy_targets = {
    EffectTarget.at_least_one_enemy,
    EffectTarget.enemy_single,
    EffectTarget.enemy_team,
    EffectTarget.enemy_team_all_at_once,
    EffectTarget.multi_target_enemy,
    EffectTarget.preselected_enemy_single
}

aoe_targets = {
    EffectTarget.enemy_team,
    EffectTarget.enemy_team_all_at_once,
    EffectTarget.friendly_team,
    EffectTarget.friendly_team_all_at_once
}



async def is_req_satisfied(effect: DynamicSpellEffect, req: SpellType, allow_aoe: bool = False) -> bool:
    eff_type = await effect.effect_type()
    target = await effect.effect_target()
    param = await effect.effect_param()
    rounds = await effect.num_rounds()

    _aoe_targets = aoe_targets
    if not allow_aoe:
        _aoe_targets = {}


    def is_blade() -> bool:
        return all((
            eff_type in charm_effects,
            target in ally_targets.difference(_aoe_targets),
            param > 0,
            rounds == 0,
        ))

    def is_charm() -> bool:
        return all((
            eff_type in charm_effects,
            target in enemy_targets.difference(_aoe_targets),
            param < 0,
            rounds == 0,
        ))

    def is_ward() -> bool:
        return all((
            eff_type in ward_effects,
            target in ally_targets.difference(_aoe_targets),
            param < 0,
            rounds == 0,
        ))

    def is_trap() -> bool:
        return all((
            eff_type in ward_effects,
            target in enemy_targets.difference(_aoe_targets),
            param > 0,
            rounds == 0,
        ))
    
    def is_aura() -> bool:
        return all((
            eff_type in charm_effects.union(ward_effects),
            target is EffectTarget.self,
            rounds > 0,
        ))
    
    def is_basic_hanging_effect():
        return any((is_blade(), is_charm(), is_ward(), is_trap(), is_aura()))
    
    print(req)
    print(eff_type)
    print(param)
    print(target)
    print(rounds)

    match req:
        case SpellType.type_damage:
            if is_basic_hanging_effect():
                return eff_type in buff_damage_effects
            
            return eff_type in damage_effects and target in enemy_targets.difference(_aoe_targets)
        
        case SpellType.type_aoe:
            return target in aoe_targets
        
        case SpellType.type_heal:
            if is_basic_hanging_effect():
                return eff_type in buff_heal_effects
            
            return eff_type in heal_effects and target in ally_targets.difference(_aoe_targets)
        
        case SpellType.type_heal_self:
            return eff_type in heal_effects and target in (EffectTarget.self, EffectTarget.friendly_team)
        
        case SpellType.type_heal_other: #TODO: Figure out why this even exists - slack
            return eff_type in heal_effects and target in (EffectTarget.friendly_single, EffectTarget.friendly_single_not_me)
        
        case SpellType.type_blade:
            return is_blade()
        
        case SpellType.type_charm:
            return is_charm() and target in enemy_targets.difference(_aoe_targets)
        
        case SpellType.type_shield:
            return is_ward() and target in ally_targets.difference(_aoe_targets)
        
        case SpellType.type_trap:
            return is_trap() and target in enemy_targets.difference(_aoe_targets)
        
        case SpellType.type_enchant:
            return target is EffectTarget.spell
        
        case SpellType.type_aura:
            return is_aura()
        case SpellType.type_global:
            return all(
                eff_type in charm_effects.union(ward_effects),
                target is EffectTarget.target_global,
            )
        
        case SpellType.type_polymorph:
            return eff_type is SpellEffects.polymorph
        
        case SpellType.type_shadow:
            return eff_type is SpellEffects.shadow_self
        
        case SpellType.type_shadow_creature:
            return eff_type is SpellEffects.shadow_creature
        

async def conditional_subeffect_check(effect: DynamicSpellEffect) -> DynamicSpellEffect:
    output_effect = effect

    target = await effect.effect_target()
    eff_type = await effect.effect_type()

    if target == EffectTarget.invalid_target or eff_type == SpellEffects.invalid_spell_effect:
        try:
            subeffects = await effect.maybe_effect_list()
            if len(subeffects) != 0:
                output_effect = subeffects[0]

        except ValueError:
            pass

    return output_effect


async def does_card_contain_reqs(card: CombatCard, template: TemplateSpell) -> bool:
    print(2)
    effects = await get_inner_card_effects(card)
    print(3)
    is_aoe_req = SpellType.type_aoe in template.requirements
    matched_reqs = 0
    needed_matches = len(template.requirements)
    for req in template.requirements:
        for e in effects:
            effect = await conditional_subeffect_check(e)
            print(4)
            if await is_req_satisfied(effect, req, is_aoe_req):
                print(5)
                matched_reqs += 1
                break

    return matched_reqs == needed_matches



class SprintyCombat(CombatHandler):
    def __init__(self, client: wizwalker.client.Client, config_provider: BaseCombatBackend, handle_mouseless: bool = False):
        super().__init__(client)
        self.client: wizwalker.client.Client = client # to restore autocomplete
        self.config = config_provider
        self.turn_adjust = 0
        self.cur_card_count = 0
        self.prev_card_count = 0
        self.was_pass = False
        self.had_first_round = False
        self.rel_round_offset = 0
        self.handle_mouseless = handle_mouseless

    async def handle_combat(self):
        self.turn_adjust = 0
        self.cur_card_count = 0
        self.prev_card_count = 0
        self.rel_round_offset = 0
        self.was_pass = False
        self.had_first_round = False
        await super().handle_combat()

    async def get_member_named(self, name: str) -> Optional[CombatMember]:
        # Issue: #4
        async def _inner():
            members: List[CombatMember] = await self.get_members()

            for member in members:
                if name == await member.name():
                    return member
            return None
        try:
            return await wizwalker.utils.maybe_wait_for_value_with_timeout(
                _inner,
                timeout=2.0
            )
        except wizwalker.errors.ExceptionalTimeout:
            return None

    async def get_member_vaguely_named(self, name: str) -> Optional[CombatMember]:
        # Issue #4
        async def _inner():
            members = await self.get_members()

            for member in members:
                if name.lower() in (await member.name()).lower():
                    return member
            return None
        try:
            return await wizwalker.utils.maybe_wait_for_value_with_timeout(
                _inner,
                timeout=2.0
            )
        except wizwalker.errors.ExceptionalTimeout:
            return None

    async def pass_button(self):
        self.was_pass = True
        await super().pass_button()

    async def get_cards(self) -> List[CombatCard]:  # extended to sort by enchanted
        async def _inner() -> List[CombatCard]:
            cards = await super(SprintyCombat, self).get_cards()
            rese, res = [], []
            for card in cards:
                if await card.is_enchanted():
                    rese.append(card)
                else:
                    res.append(card)
            return rese + res
        try:
            return await wizwalker.utils.maybe_wait_for_any_value_with_timeout(_inner, sleep_time=0.2, timeout=2.0)
        except wizwalker.errors.ExceptionalTimeout:
            return []

    async def get_card_named(self, name: str) -> Optional[CombatCard]:
        try:
            return await super().get_card_named(name)
        except ValueError:
            return None

    async def get_card_with_predicate(self, pred: Callable) -> Optional[CombatCard]:
        cards = await self.get_cards_with_predicate(pred)
        if len(cards) > 0:
            return cards[0]
        return None

    async def get_card_vaguely_named(self, name: str) -> Optional[CombatCard]:
        async def _pred(card: CombatCard):
            return name.lower() in (await card.name()).lower()

        return await self.get_card_with_predicate(_pred)

    async def get_card_counts(self) -> Tuple[int, int]:
        # Issue: #6. Very rare error
        async def _inner():
            window = None
            while window is None:
                window, *_ = await self.client.root_window.get_windows_with_name("CountText")
            text: str = await window.maybe_text()
            _, count_text = text.splitlines()
            count_text = count_text[8:-9]
            count_text = count_text.replace("of", "").strip()  # I know this sucks
            res1, res2 = count_text.split()
            return int(res1), int(res2)
        try:
            return await wizwalker.utils.maybe_wait_for_any_value_with_timeout(_inner, sleep_time=0.2, timeout=2.0)
        except wizwalker.errors.ExceptionalTimeout:
            return (0, 0) # TODO: Maybe propagate, but good enough for now

    async def get_castable_cards(self) -> List[CombatCard]:  # extension for castable cards only
        async def _pred(card: CombatCard):
            return await card.is_castable()

        return await self.get_cards_with_predicate(_pred)

    async def get_castable_cards_named(self, name: str) -> List[CombatCard]:
        cards = await self.get_castable_cards()
        res = []

        for card in cards:
            if name == await card.name():
                res.append(card)

        return res

    async def get_castable_cards_vaguely_named(self, name: str) -> List[CombatCard]:
        cards = await self.get_castable_cards()
        res = []
        for card in cards:
            if name.lower() in (await card.name()).lower():
                res.append(card)

        return res

    async def get_castable_card_named(self, name: str, only_enchants=False) -> Optional[CombatCard]:  # extension to get only castable card
        cards = await self.get_castable_cards()

        for card in cards:
            if name == await card.name():
                if only_enchants:
                    for e in await card.get_spell_effects():
                        if await e.effect_target() is EffectTarget.spell:
                            return card
                    else:
                        continue
                return card

        return None

    async def get_castable_card_vaguely_named(self, name: str, only_enchants=False) -> Optional[CombatCard]:
        cards = await self.get_castable_cards()

        for card in cards:
            if name.lower() in (await card.name()).lower():
                if only_enchants:
                    for e in await card.get_spell_effects():
                        if await e.effect_target() is EffectTarget.spell:
                            return card
                    else:
                        continue
                return card

        return None

    async def get_castable_enchanted_card_named(self, name: str) -> Optional[CombatCard]:
        for s in await self.get_castable_cards_named(name):
            if await s.is_enchanted():
                return s
        return None

    async def get_castable_enchanted_card_vaguely_named(self, name: str) -> Optional[CombatCard]:
        for s in await self.get_castable_cards_vaguely_named(name):
            if await s.is_enchanted():
                return s
        return None

    async def get_cards_by_template(self, template: TemplateSpell) -> List[CombatCard]:
        print(1)
        try:
            cards = await self.get_castable_cards()
        except Exception as e:
            print(e)
        res = []
        for c in cards:
            if await does_card_contain_reqs(c, template):
                res.append(c)

        return res
    



    async def get_boss_or_none(self) -> Optional[CombatMember]:
        for m in await self.get_members():
            if await m.is_boss():
                return m
        return None

    async def get_allies(self) -> List[CombatMember]:
        members = []
        my_client = await self.get_client_member()
        my_participant = await my_client.get_participant()
        my_team_id = await my_participant.team_id()
        my_id = await my_participant.owner_id_full()
        for mem in await self.get_members():
            participant = await mem.get_participant()
            if await participant.team_id() == my_team_id \
                    and await participant.owner_id_full() != my_id:
                members.append(mem)
        return members

    async def get_enemies(self) -> List[CombatMember]:
        members = []
        my_client = await self.get_client_member()
        my_participant = await my_client.get_participant()
        my_team_id = await my_participant.team_id()
        for mem in await self.get_members():
            participant = await mem.get_participant()
            if await participant.team_id() != my_team_id:
                members.append(mem)
        return members

    async def get_nth_ally_or_none(self, n: int) -> Optional[CombatMember]:
        allies = await self.get_allies()
        if len(allies) <= n:
            return None
        return allies[n]

    async def get_nth_enemy_or_none(self, n: int) -> Optional[CombatMember]:
        enemies = await self.get_enemies()
        if len(enemies) <= n:
            return None
        return enemies[n]

    async def try_get_config_target(self, target: TargetData) -> Union[bool, Optional[CombatMember]]:
        ttype = None
        data = None
        if target is not None:
            ttype = target.target_type
            data = target.extra_data
        else:
            return None

        if ttype is TargetType.type_boss:
            if boss := await self.get_boss_or_none():
                return boss
        elif ttype is TargetType.type_self:
            return await self.get_client_member()
        elif ttype is TargetType.type_aoe:
            return None
        elif ttype is TargetType.type_enemy:
            if data is None:
                if enemy := await self.get_nth_enemy_or_none(0):
                    return enemy
            else:
                if enemy := await self.get_nth_enemy_or_none(data):
                    return enemy
        elif ttype is TargetType.type_ally:
            if data is None:
                if ally := await self.get_nth_ally_or_none(0):
                    return ally
            else:
                if ally := await self.get_nth_ally_or_none(data):
                    return ally
        elif ttype is TargetType.type_named:
            if target.is_literal:
                if res := await self.get_member_named(data):
                    return res
            if res := await self.get_member_vaguely_named(data):
                return res

        return False

    async def try_get_spell(self, spell: Spell, only_enchants=False) -> Union[CombatCard, str, None]:
        if isinstance(spell, NamedSpell):
            spell: NamedSpell
            if spell.name in ("pass", "none"):
                return spell.name
            if spell.is_literal:
                return await self.get_castable_card_named(spell.name, only_enchants)
            else:
                return await self.get_castable_card_vaguely_named(spell.name, only_enchants)
        elif isinstance(spell, TemplateSpell):
            spell: TemplateSpell
            res = await self.get_cards_by_template(spell)
            print(res)
            if len(res) > 0:
                return res[0]
            return None
        else:
            raise NotImplementedError("Unknown spell config type")

    async def try_execute_config(self, move_config: MoveConfig) -> bool:
        cur_card = await self.try_get_spell(move_config.move.card)
        if cur_card is None:
            return False

        if cur_card == "pass":
            print("declared pass fail")
            await self.pass_button()
            return True

        target = await self.try_get_config_target(move_config.target)

        if target == False:  # Wouldn't want a None to mess it up
            return False

        if move_config.move.enchant is not None and not await cur_card.is_enchanted():
            enchant_card = await self.try_get_spell(move_config.move.enchant, only_enchants=True)
            if enchant_card != "none":
                if enchant_card is not None:
                    # Issue: 5. Casting wasn't that reliable
                    pre_enchant_count = len(await self.get_cards())
                    while len(await self.get_cards()) == pre_enchant_count:
                        await enchant_card.cast(cur_card, sleep_time=self.config.cast_time*2)
                        await asyncio.sleep(self.config.cast_time*2) # give it some time for card list to update

                    self.cur_card_count -= 1

                elif enchant_card is None and (isinstance(move_config.move.enchant, TemplateSpell) and not move_config.move.enchant.optional):
                    return False

        to_cast = await self.try_get_spell(move_config.move.card)
        if to_cast is None:
            return False  # this should not happen
        
        # Issue: 5. Casting wasn't that reliable
        try:
            while to_cast != None:
                try: 
                    await to_cast.cast(target, sleep_time=self.config.cast_time)
                    await asyncio.sleep(self.config.cast_time) # give it some time for card list to update
                    to_cast = await self.try_get_spell(move_config.move.card)
                except ValueError:
                    break # Issue: 8
        except wizwalker.errors.WizWalkerMemoryError or ValueError:
            pass # Let it happen if it happens
        return True

    async def fail_turn(self):
        self.turn_adjust -= 1
        print("fail turn")
        await self.pass_button()

    async def on_fizzle(self):
        self.turn_adjust -= 1

    async def handle_round(self):
        # try:
        #     await self.client.mouse_handler.activate_mouseless()
        # except wizwalker.errors.HookAlreadyActivated:
        #     pass
        async with self.client.mouse_handler:
            try:
                self.config.attach_combat(self) # For safety. Could probably also do this in handle_combat

                real_round = await self.round_number()
                self.cur_card_count = len(await self.get_cards()) + (await self.get_card_counts())[0]

                if not self.had_first_round:
                    current_round = real_round - 1
                    if current_round > 0:
                        self.turn_adjust -= current_round
                else:
                    if self.cur_card_count >= self.prev_card_count and not self.was_pass:
                        await self.on_fizzle()

                self.was_pass = False
                current_round = (real_round - 1 + self.turn_adjust + self.rel_round_offset)

                # Issue: #3. Need to make sure it's valid
                member: CombatMember = None
                try:
                    member = await wizwalker.utils.maybe_wait_for_any_value_with_timeout(
                        self.get_client_member,
                        timeout=2.0
                    )
                except wizwalker.errors.ExceptionalTimeout:
                    # TODO: Maybe make this more dramatic
                    await self.fail_turn() # This is quite catastrophic. Use default fail for now
                
                if member is not None:
                    if await member.is_stunned():
                        await self.fail_turn()
                    else:
                        round_config = await self.config.get_real_round(real_round)
                        if round_config is None:
                            round_config = await self.config.get_relative_round(current_round)
                        else:
                            self.rel_round_offset -= 1

                        if round_config is not None:
                            for p in round_config.priorities:  # go through rounds priorities
                                if await self.try_execute_config(p):
                                    break  # we found a working priority and managed to cast it
                            else:
                                print("round config fail")
                                await self.pass_button()
                        else:  # Very bad. Probably using empty config
                            await self.config.handle_no_cards_given()

                self.had_first_round = True  # might go bad on throw
                self.prev_card_count = self.cur_card_count
            finally:
                if self.handle_mouseless:
                    try:
                        await self.client.mouse_handler.deactivate_mouseless()
                    except wizwalker.errors.HookNotActive:
                        pass
