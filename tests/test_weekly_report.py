import unittest
from datetime import datetime
from decimal import Decimal as D
from dataclasses import replace
from weekly_control import *
from weekly_control_data import WeeklySourceData

NOW=datetime(2026,10,14,12,tzinfo=SAO_PAULO)
ID=ProjectIdentity('FEMSA','DISPLAY','1','VM')
def source(rem='152', ret='124'):
    return WeeklySourceData(150,160,(ComponentRequirement('CORPO','CORPO',D(1),0,True),), (MovementEntry('CORPO','remessa',D(rem),NOW),MovementEntry('CORPO','retorno',D(ret),NOW)),('CORPO',),NOW,())

class ReportTest(unittest.TestCase):
    def api(self):
        try:
            from weekly_report import snapshot, changes
        except ImportError:
            self.fail('Snapshot and cumulative report feature missing')
        return snapshot,changes
    def test_three_emissions_accumulate_and_exclude_unchanged(self):
        snapshot,changes=self.api()
        first=snapshot(ID,source()); self.assertEqual(len(changes(first,None)),1)
        second=snapshot(ID,source('162')); row=changes(second,first)[0]
        self.assertEqual(row['current']['total_remessa'],'162')
        self.assertEqual(row['current']['total_retorno'],'124')
        self.assertEqual(row['current']['painting_balance'],'38')
        self.assertEqual(row['deltas']['total_remessa'],'10')
        third=snapshot(ID,source('162','130')); row=changes(third,second)[0]
        self.assertEqual(row['deltas']['total_retorno'],'6')
        self.assertEqual(row['current']['painting_balance'],'32')
        self.assertEqual(changes(third,third),[])
    def test_corrections_metadata_targets_missing_removed_and_backdated(self):
        snapshot,changes=self.api(); old=snapshot(ID,source())
        self.assertEqual(changes(snapshot(ID,source('140')),old)[0]['deltas']['total_remessa'],'-12')
        for altered in (replace(source(),current_target=170),replace(source(), requirements=(ComponentRequirement('CORPO','NOVO',D(2),0,True),)),replace(source(),entries=(MovementEntry('CORPO','remessa',D('152'),NOW.replace(day=1)),MovementEntry('CORPO','retorno',D('124'),NOW)))):
            self.assertEqual(len(changes(snapshot(ID,altered),old)),1)
        removed=snapshot(ID,replace(source(),requirements=(),entries=(),detected_component_keys=()))
        self.assertTrue(changes(removed,old)[0]['removed'])
        missing=snapshot(ID,replace(source(),entries=()))
        zero=snapshot(ID,source('0','0'))
        self.assertNotEqual(missing,zero)
    def test_replacement_entry_id_with_equal_totals_is_visible(self):
        snapshot,changes=self.api()
        old=replace(source(),source_entries=({'id':1,'processo':'ENVIO CORPO','quantidade':'152'},))
        new=replace(source(),source_entries=({'id':2,'processo':'ENVIO CORPO','quantidade':'152'},))
        self.assertEqual(len(changes(snapshot(ID,new),snapshot(ID,old))),1)
    def test_display_order_change_is_reported(self):
        snapshot,changes=self.api()
        edited=replace(source(),requirements=(ComponentRequirement('CORPO','CORPO',D(1),4,True),))
        self.assertEqual(len(changes(snapshot(ID,edited),snapshot(ID,source()))),1)
    def test_decimal_normalization_and_project_scope(self):
        snapshot,changes=self.api()
        self.assertEqual(changes(snapshot(ID,source('152.000')),snapshot(ID,source())),[])
        self.assertNotEqual(snapshot(ID,source())['project_key'],snapshot(replace(ID,numero_display='2'),source())['project_key'])

if __name__=='__main__': unittest.main()
