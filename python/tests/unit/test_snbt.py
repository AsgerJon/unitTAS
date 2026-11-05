"""
Tests of unittas.snbt: NBT as modern SNBT text (PROTOCOL.md section 5.6), read into a typed tree that still knows a
byte from an int, and written back.

  python -m unittest discover -s python/tests/unit
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from unittas.snbt import Byte, ByteArray, Compound, Double, Float, Int, IntArray, Long, Short, String, TagList
from unittas.snbt import dumps, loads


class ReadTests(unittest.TestCase):

  def test_every_number_knows_its_type(self) -> None:
    tree = loads('{b:1b,s:2s,i:3,l:4L,f:5.5f,d:6.25d}')
    self.assertEqual({'b': 1, 's': 2, 'i': 3, 'l': 4, 'f': 5.5, 'd': 6.25}, tree)
    self.assertEqual([Byte, Short, Int, Long, Float, Double], [type(tree[key]) for key in 'bsilfd'])

  def test_a_number_without_a_suffix(self) -> None:
    self.assertIs(Int, type(loads('7')))
    self.assertIs(Double, type(loads('7.5')))
    self.assertIs(Double, type(loads('1e3')))

  def test_suffixes_in_either_case(self) -> None:
    self.assertEqual([Byte, Short, Long, Float, Double],
                     [type(loads(text)) for text in ('1B', '2S', '3l', '4F', '5D')])

  def test_strings(self) -> None:
    self.assertEqual('a "quoted" \\ word', loads('"a \\"quoted\\" \\\\ word"'))
    self.assertEqual("it's", loads("'it\\'s'"))
    self.assertIs(String, type(loads('"x"')))
    self.assertEqual('minecraft:stone', loads('{id:minecraft:stone}')['id'], 'an unquoted word is a string')

  def test_true_and_false_are_bytes(self) -> None:
    tree = loads('{yes:true,no:false}')
    self.assertEqual((1, 0), (tree['yes'], tree['no']))
    self.assertIs(Byte, type(tree['yes']))

  def test_lists_and_arrays(self) -> None:
    tree = loads('{list:[1,2,3],bytes:[B;1b,2b],ints:[I;1,2],longs:[L;5L],empty:[],nested:[{a:1},{a:2}]}')
    self.assertIs(TagList, type(tree['list']))
    self.assertEqual([1, 2, 3], tree['list'])
    self.assertIs(ByteArray, type(tree['bytes']))
    self.assertEqual([1, 2], tree['bytes'])
    self.assertIs(IntArray, type(tree['ints']))
    self.assertEqual([], tree['empty'])
    self.assertEqual(2, tree['nested'][1]['a'])

  def test_a_compound_reads_as_a_dict(self) -> None:
    tree = loads('{display:{Name:"Red"},ench:[{id:16s,lvl:5s}]}')
    self.assertIs(Compound, type(tree))
    self.assertEqual('Red', tree['display']['Name'])
    self.assertIs(Short, type(tree['ench'][0]['lvl']))

  def test_spaces_between(self) -> None:
    self.assertEqual({'a': 1, 'b': [2, 3]}, loads(' { a : 1 , b : [ 2 , 3 ] } '))

  def test_broken_text_is_refused(self) -> None:
    for text in ('{a:1', '{a 1}', '[1,2', '{a:1}}', '"open', '[B;1,2]', ''):
      with self.subTest(text=text):
        with self.assertRaises(ValueError):
          loads(text)


class WriteTests(unittest.TestCase):

  def test_round_trip(self) -> None:
    text = ('{b:1b,s:2s,i:3,l:4L,f:5.5f,d:6.25d,str:"seven",list:[1,2,3],bytes:[B;1b,2b],ints:[I;1,2],'
            'comp:{x:1},"odd key":"v"}')
    self.assertEqual(loads(text), loads(dumps(loads(text))))
    self.assertEqual(text, dumps(loads(text)))

  def test_plain_python_values_get_the_obvious_types(self) -> None:
    self.assertEqual('{a:1,b:2.5d,c:"x",d:[1,2]}', dumps({'a': 1, 'b': 2.5, 'c': 'x', 'd': [1, 2]}))
    self.assertEqual('1b', dumps(True))

  def test_escapes(self) -> None:
    self.assertEqual('"say \\"hi\\" \\\\ there"', dumps('say "hi" \\ there'))

  def test_typed_values_written_as_their_type(self) -> None:
    self.assertEqual('[3s,4s]', dumps(TagList([Short(3), Short(4)])))
    self.assertEqual('[I;1,2]', dumps(IntArray([1, 2])))


if __name__ == '__main__':
  unittest.main()
