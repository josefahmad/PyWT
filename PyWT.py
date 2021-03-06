#!/usr/bin/env python
'''
Based on https://github.com/wiredtiger/wiredtiger/blob/master/examples/python/ex_access.py
'''

from __future__ import print_function
from blessings import Terminal
from bson import json_util
from pprint import pformat
from wiredtiger import wiredtiger_open
import argparse
import bson
import os

class PyWT(object):
    ''' Python WiredTiger '''

    def __init__(self, dbpath):
        ''' Connect to the database and open a session '''
        conn = wiredtiger_open(dbpath, 'create')
        self.session = conn.open_session()
        self.dbpath = dbpath

    @staticmethod
    def bson_decode(content):
        ''' Returns decoded BSON obect '''
        return bson.BSON.decode(bson.BSON(content))

    def export_table_name(self, namespace):
        ''' Find the corresponding WT table name from MongoDB namespace '''
        cursor = self.session.open_cursor('table:_mdb_catalog', None)
        for _, value in cursor:
            val = PyWT.bson_decode(value)
            if val.get('ns') == namespace:
                return self.dump_table(str(val.get('ident')), raw=False, pretty=False)
        return ''

    def export_all(self):
        ''' Export all namespaces. Skip over any collection with missing files '''
        cursor = self.session.open_cursor('table:_mdb_catalog', None)
        output = []
        for _, value in cursor:
            val = PyWT.bson_decode(value)
            namespace = val.get('ns')
            ident = val.get('ident')
            if not namespace or not os.path.isfile(ident + '.wt'):
                continue
            if os.path.isfile(ident + '.wt'):
                print('Exporting', namespace, '...', end=' ')
                with open(namespace + '.json', 'w') as outfile:
                    outfile.write(self.dump_table(str(ident), raw=False, pretty=False))
                print('done')
        return True

    def insert_table(self, table):
        ''' Insert 5 records into the table '''
        self.session.create('table:'+table, 'key_format=S,value_format=S')
        self.session.begin_transaction()
        cursor = self.session.open_cursor('table:'+table, None)
        for idx in range(5):
            cursor.set_key('key' + str(idx))
            cursor.set_value('value' + str(idx))
            cursor.insert()
        self.session.rollback_transaction()
        return True

    def dump_table(self, table, raw, pretty):
        ''' Dump the table contents (assumes BSON-encoded) '''
        cursor = self.session.open_cursor('table:'+table, None)
        output = ''
        for key, value in cursor:
            if not raw:
                val = PyWT.bson_decode(value)
            else:
                val = value
            if pretty:
                output += '-----Key: {key}-----\n{val}\n\n'.format(key=key, val=pformat(val))
            else:
                output += '{val}\n'.format(val=json_util.dumps(val))
        cursor.close()
        return output

    def dump_catalog(self):
        ''' Dump the _mdb_catalog table '''
        term = Terminal()
        cursor = self.session.open_cursor('table:_mdb_catalog', None)
        sizes = self.session.open_cursor('table:sizeStorer', None)
        output = ''
        for _, value in cursor:
            val = PyWT.bson_decode(value)
            table = val.get('ident')
            namespace = val.get('ns')
            indexes = val.get('idxIdent')

            if not namespace:
                continue
            diskfile = self.dbpath + os.sep + table + '.wt'

            if namespace.startswith('admin') or namespace.startswith('local') or namespace.startswith('config'):
                namespacestring = term.yellow + namespace + term.normal
            else:
                namespacestring = term.blue + namespace + term.normal
            print('MongoDB namespace : {ns}'.format(ns=namespacestring))
            print('WiredTiger table  : {tbl}'.format(tbl=table))
            if not os.path.isfile(diskfile):
                print(term.red + '*** Collection file ' + table + '.wt not found ***' + term.normal)

            sizes.set_key('table:'+str(table))
            if sizes.search() == 0:
                if not os.path.exists(diskfile):
                    print()
                    continue
                diskfilesize = os.path.getsize(diskfile)
                wtsizes = PyWT.bson_decode(sizes.get_value())
                datasize = wtsizes.get('dataSize')
                numrecords = wtsizes.get('numRecords')
                print('File Size         : {0} bytes ({1} MB)'.format(diskfilesize, diskfilesize / 1024**2))
                print('Data Size         : {0} bytes ({1} MB)'.format(datasize, datasize / 1024**2))
                print('Space Utilization : {0} %'.format(round(datasize * 100.0 / diskfilesize, 2)))
                print('Num Records       : {0}'.format(numrecords))

            if indexes:
                indexsize = 0
                print('Indexes :')
                for index in sorted(indexes):
                    indexdiskfile = self.dbpath + os.sep + indexes.get(index) + '.wt'
                    if not os.path.isfile(indexdiskfile):
                        print(term.red + '    *** Index file ' + indexes.get(index) + '.wt not found ***' + term.normal)
                    else:
                        indexdiskfilesize = os.path.getsize(indexdiskfile)
                        print(term.green + '    {0}'.format(index) + term.normal + ' : {0}'.format(indexes.get(index)) +
                              '    Size: {0} bytes ({1} MB)'.format(indexdiskfilesize, indexdiskfilesize / 1024**2))
                        indexsize = indexdiskfilesize

            print('Total namespace size : {0} bytes ({1} MB)'.format(datasize + indexsize, (datasize+indexsize) / 1024**2))
            print()
        cursor.close()
        sizes.close()
        return output


if __name__ == '__main__':
    # pylint: disable=invalid-name
    parser = argparse.ArgumentParser()
    parser.add_argument('--dbpath', default='.', help='dbpath (default is current directory)')
    parser.add_argument('--list', action='store_true', help='print MongoDB catalog content')
    parser.add_argument('--raw', action='store_true', help='print raw data')
    parser.add_argument('--pretty', action='store_true', help='pretty print documents')
    parser.add_argument('--table', help='WT table to print')
    parser.add_argument('--export', help='MongoDB namespace to export')
    parser.add_argument('--export-all', action='store_true', help='Export all namespaces')
    args = parser.parse_args()

    wt = PyWT(args.dbpath)
    if args.list:
        print(wt.dump_catalog())
    elif args.table:
        print(wt.dump_table(args.table, args.raw, args.pretty))
    elif args.export:
        print(wt.export_table_name(args.export))
    elif args.export_all:
        wt.export_all()
    else:
        print(wt.dump_catalog())
