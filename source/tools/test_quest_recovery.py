"""Regression cases for ownership boundaries and previously omitted calls."""
import unittest
from recover_quest_sources import Sources, dedicated_dungeon_maps, ordered_items, scene_text


def source_fixture():
    source = Sources.__new__(Sources)
    source.tables = {
        'quest': {'1': {'Reference': ['q_2', 'f_10_1', 'e_8_7', 'l_8_4']}},
        'flow': {'story_1_1': [{'Name': 'TeleportDungeon', 'Params': {
            'DungeonId': 5, 'TransitionOption': {'CenterTextFlow': {
                'FlowListName': 'story', 'FlowId': 2, 'StateId': 1}}}}],
            'story_2_1': [{'Name': 'ChangeState', 'Params': {'StateId': 1}}],
            'entity_1_1': [], 'dungeon_1_1': [], 'world_1_1': []},
        'level': {'4': {'LevelId': 8, 'Reference': ['f_11_1']},
                  '6': {'LevelId': 100, 'Reference': ['f_12_1']}},
        'recall': {},
    }
    source.node_groups = {'quest': {}, 'level': {}}
    source.flow_ids = {10: 'story', 11: 'entity', 12: 'dungeon'}
    source.states_by_flow = {'story_1': ['story_1_1'], 'entity_1': ['entity_1_1'],
                             'dungeon_1': ['dungeon_1_1']}
    source.entities = {(8, 7): b''}
    source.entity_cache = {(8, 7): {'Flow': {'FlowListName': 'entity', 'FlowId': 1, 'StateId': 1}}}
    source.dungeons = {'5': 100}
    source.levels_by_map = {100: ['6']}
    return source


class RecoveryTests(unittest.TestCase):
    def test_mixed_quest_world_map_is_not_a_dedicated_dungeon(self):
        levels = {'a': {'LevelId': 907, 'Type': 'Dungeon'},
                  'b': {'LevelId': 907, 'Type': 'Quest'},
                  'c': {'LevelId': 1555, 'Type': 'Dungeon'}}
        self.assertEqual(dedicated_dungeon_maps(levels), {1555})

    def test_nested_transition_and_private_dungeon_followed(self):
        states, proof, missing = source_fixture().closure('1', [])
        self.assertEqual(set(states), {'story_1_1', 'story_2_1', 'entity_1_1', 'dungeon_1_1'})
        self.assertIn('CenterTextFlow', proof('story_2_1')[-1])
        self.assertTrue(any('MapConfigId/100' in step for step in proof('dungeon_1_1')))
        self.assertEqual(missing, [])

    def test_prerequisite_and_shared_world_not_merged(self):
        source = source_fixture()
        source.tables['quest']['2'] = {'Reference': ['f_13_1']}
        source.flow_ids[13] = 'world'
        source.states_by_flow['world_1'] = ['world_1_1']
        source.tables['flow']['story_1_1'].append({'Name': 'TeleportDungeon', 'Params': {'DungeonId': 8}})
        states, _, _ = source.closure('1', [])
        self.assertNotIn('world_1_1', states)

    def test_wrong_map_levelplay_token_rejected(self):
        source = source_fixture()
        source.tables['quest']['1'] = {'Reference': ['l_99_4']}
        states, _, _ = source.closure('1', [])
        self.assertEqual(states, [])

    def test_source_sequence_choices_and_unvisited_items_preserved(self):
        items = [{'Id': 1}, {'Id': 2}, {'Id': 3}]
        self.assertEqual([(n, v['Id']) for n, v in ordered_items({'TalkItems': items, 'TalkSequence': [[2, 99, 1], [2]]})],
                         [(0, 2), (0, 1), ('자료순서', 3)])

    def test_duplicate_talk_item_fails_closed(self):
        with self.assertRaises(ValueError):
            ordered_items({'TalkItems': [{'Id': 1}, {'Id': 1}]})

    def test_screen_text_and_choice_are_readable_and_keep_source(self):
        rows = [dict(kind='대사', speaker='화면 문구', talk_id=1, status='OK', text='사명은, 끝없는 족쇄가 됐다', transition=''),
                dict(kind='선택지', speaker='플레이어 선택지', option=1, status='OK', text='선택', transition='대화ID 2로 이동')]
        text = scene_text(7, 'state_72_1', rows, ['level:4/Reference/1'])
        self.assertIn('장면 7: 추가 원문', text)
        self.assertIn('[대화ID 1] 화면 문구: 사명은, 끝없는 족쇄가 됐다', text)
        self.assertIn('  선택 1: 선택\n    → 대화ID 2로 이동', text)
        self.assertIn('대화 묶음 연결 근거: level:4/Reference/1', text)


if __name__ == '__main__':
    unittest.main()
