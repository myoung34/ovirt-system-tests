# -*- coding: utf-8 -*-
#
# Copyright 2014, 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
import functools
from os import EX_OK
import nose.tools as nt
from nose import SkipTest

from ovirtsdk.xml import params

from lago import utils
from ovirtlago import testlib

import ovirtsdk4.types as types

import time

MB = 2 ** 20
GB = 2 ** 30
# the default MAC pool has addresses like 00:1a:4a:16:01:51
UNICAST_MAC_OUTSIDE_POOL = '0a:1a:4a:16:01:51'

TEST_DC = 'test-dc'
TEST_CLUSTER = 'test-cluster'
TEMPLATE_BLANK = 'Blank'
TEMPLATE_CENTOS7 = 'centos7_template'
TEMPLATE_CIRROS = 'CirrOS_0.3.5_for_x86_64_glance_template'

SD_NFS_NAME = 'nfs'
SD_SECOND_NFS_NAME = 'second-nfs'
SD_ISCSI_NAME = 'iscsi'

VM0_NAME = 'vm0'
VM1_NAME = 'vm1'
VM2_NAME = 'vm2'
VM0_PING_DEST = VM0_NAME
VMPOOL_NAME = 'test-pool'
DISK0_NAME = '%s_disk0' % VM0_NAME
DISK1_NAME = '%s_disk1' % VM1_NAME
DISK2_NAME = '%s_disk2' % VM2_NAME
GLANCE_DISK_NAME = 'CirrOS_0.3.5_for_x86_64_glance_disk'

SD_ISCSI_HOST_NAME = testlib.get_prefixed_name('engine')
SD_ISCSI_TARGET = 'iqn.2014-07.org.ovirt:storage'
SD_ISCSI_PORT = 3260
SD_ISCSI_NR_LUNS = 2
DLUN_DISK_NAME = 'DirectLunDisk'
SD_TEMPLATES_NAME = 'templates'

VM_NETWORK = u'VM Network with a very long name and עברית'
NETWORK_FILTER_NAME = 'clean-traffic'
NETWORK_FILTER_PARAMETER0_NAME = 'CTRL_IP_LEARNING'
NETWORK_FILTER_PARAMETER0_VALUE = 'dhcp'
NETWORK_FILTER_PARAMETER1_NAME = 'DHCPSERVER'

SNAPSHOT_DESC_1 = 'dead_snap1'
SNAPSHOT_DESC_2 = 'dead_snap2'


def _get_network_fiter_parameters_service(engine):
    nics_service = _get_nics_service(engine)
    nic = nics_service.list()[0]
    return nics_service.nic_service(id=nic.id)\
        .network_filter_parameters_service()


def _get_nics_service(engine):
    vm_service = _get_vm_service(engine, VM0_NAME)
    nics_service = vm_service.nics_service()
    return nics_service


def _get_vm_service(engine, vmname):
    vms_service = engine.vms_service()
    vm = vms_service.list(search=vmname)[0]
    if vm is None:
        return None
    return vms_service.vm_service(vm.id)


def _get_disk_service(engine, diskname):
    disks_service = engine.disks_service()
    disk = disks_service.list(search=diskname)[0]
    return disks_service.disk_service(disk.id)


def _get_storage_domain_service(engine, sd_name):
    storage_domains_service = engine.storage_domains_service()
    sd = storage_domains_service.list(search=sd_name)[0]
    return storage_domains_service.storage_domain_service(sd.id)


def _get_storage_domain_vm_service_by_name(sd_service, vm_name):
    vms_service = sd_service.vms_service()
    # StorageDomainVmsService.list has no 'search' parameter and ignores
    # query={'name': 'spam'} so we have to do the filtering ourselves
    vm = next(vm for vm in vms_service.list() if vm.name == vm_name)
    return vms_service.vm_service(vm.id)


def _ping(ovirt_prefix, destination):
    """
    Ping a given destination.
    """
    host = ovirt_prefix.virt_env.host_vms()[0]
    cmd = ['ping', '-4', '-c', '1']
    ret = host.ssh(cmd + [destination])
    return ret.code


@testlib.with_ovirt_api
def add_vm_blank(api):
    vm_memory = 256 * MB
    vm_params = params.VM(
        memory=vm_memory,
        os=params.OperatingSystem(
            type_='other_linux',
        ),
        type_='server',
        high_availability=params.HighAvailability(
            enabled=False,
        ),
        cluster=params.Cluster(
            name=TEST_CLUSTER,
        ),
        template=params.Template(
            name=TEMPLATE_BLANK,
        ),
        display=params.Display(
            smartcard_enabled=True,
            keyboard_layout='en-us',
            file_transfer_enabled=True,
            copy_paste_enabled=True,
        ),
        memory_policy=params.MemoryPolicy(
            guaranteed=vm_memory / 2,
        ),
        name=VM0_NAME
    )
    api.vms.add(vm_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM0_NAME).status.state == 'down',
    )
    vm_params.name = VM2_NAME
    vm_params.high_availability.enabled = True
    api.vms.add(vm_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM2_NAME).status.state == 'down',
    )



@testlib.with_ovirt_api
def add_nic(api):
    NIC_NAME = 'eth0'
    nic_params = params.NIC(
        name=NIC_NAME,
        interface='virtio',
        network=params.Network(
            name='ovirtmgmt',
        ),
    )
    api.vms.get(VM0_NAME).nics.add(nic_params)

    nic_params.mac = params.MAC(address=UNICAST_MAC_OUTSIDE_POOL)
    nic_params.interface='e1000'
    api.vms.get(VM2_NAME).nics.add(nic_params)


@testlib.with_ovirt_api4
def add_disk(api):
    engine = api.system_service()
    vm_service = _get_vm_service(engine, VM0_NAME)
    glance_disk = _get_disk_service(engine, GLANCE_DISK_NAME)
    nt.assert_true(vm_service and glance_disk)

    vm_service.disk_attachments_service().add(
        types.DiskAttachment(
            disk=types.Disk(
                id=glance_disk.get().id,
                storage_domains=[
                    types.StorageDomain(
                        name=SD_ISCSI_NAME,
                    ),
                ],
            ),
            interface=types.DiskInterface.VIRTIO,
            active=True,
            bootable=True,
        ),
    )

    disk_params = types.Disk(
        provisioned_size=1 * GB,
        format=types.DiskFormat.COW,
        status=None,
        sparse=True,
        active=True,
        bootable=True,
    )

    for vm_name, disk_name, sd_name in (
            (VM1_NAME, DISK1_NAME, SD_NFS_NAME),
            (VM2_NAME, DISK2_NAME, SD_SECOND_NFS_NAME)):
        disk_params.name = disk_name
        disk_params.storage_domains = [
            types.StorageDomain(
                name=sd_name,
            )
        ]

        vm_service = _get_vm_service(engine, vm_name)
        nt.assert_true(
            vm_service.disk_attachments_service().add(types.DiskAttachment(
                disk=disk_params,
                interface=types.DiskInterface.VIRTIO))
        )

    for disk_name in (GLANCE_DISK_NAME, DISK1_NAME, DISK2_NAME):
        disk_service = _get_disk_service(engine, disk_name)
        testlib.assert_true_within_short(
            lambda:
            disk_service.get().status == types.DiskStatus.OK
        )


@testlib.with_ovirt_api
def add_console(api):
    vm = api.vms.get(VM0_NAME)
    vm.graphicsconsoles.add(
        params.GraphicsConsole(
            protocol='vnc',
        )
    )
    testlib.assert_true_within_short(
        lambda:
        len(api.vms.get(VM0_NAME).graphicsconsoles.list()) == 2
    )


@testlib.with_ovirt_prefix
def add_directlun(prefix):
    # Find LUN GUIDs
    ret = prefix.virt_env.get_vm(SD_ISCSI_HOST_NAME).ssh(['cat', '/root/multipath.txt'])
    nt.assert_equals(ret.code, 0)

    all_guids = ret.out.splitlines()
    lun_guid = all_guids[SD_ISCSI_NR_LUNS]  # Take the first unused LUN. 0-(SD_ISCSI_NR_LUNS) are used by iSCSI SD

    dlun_params = types.Disk(
        name=DLUN_DISK_NAME,
        format=types.DiskFormat.RAW,
        lun_storage=types.HostStorage(
            type=types.StorageType.ISCSI,
            logical_units=[
                types.LogicalUnit(
                    address=prefix.virt_env.get_vm(SD_ISCSI_HOST_NAME).ip(),
                    port=SD_ISCSI_PORT,
                    target=SD_ISCSI_TARGET,
                    id=lun_guid,
                    username='username',
                    password='password',
                )
            ]
        ),
        sgio=types.ScsiGenericIO.UNFILTERED,
    )

    api = prefix.virt_env.engine_vm().get_api_v4()
    vm_service = _get_vm_service(api.system_service(), VM0_NAME)
    disk_attachments_service = vm_service.disk_attachments_service()
    disk_attachments_service.add(types.DiskAttachment(
        disk=dlun_params,
        interface=types.DiskInterface.VIRTIO_SCSI))

    disk_service = _get_disk_service(api.system_service(), DLUN_DISK_NAME)
    attachment_service = disk_attachments_service.attachment_service(disk_service.get().id)
    nt.assert_not_equal(
        attachment_service.get(),
        None,
        'Direct LUN disk not attached'
    )


@testlib.with_ovirt_api4
def snapshot_cold_merge(api):
    engine = api.system_service()
    vm_service = _get_vm_service(engine, VM1_NAME)

    if vm_service is None:
        raise SkipTest('Glance is not available')

    snapshots_service = vm_service.snapshots_service()
    disk = engine.disks_service().list(search=DISK1_NAME)[0]

    dead_snap1_params = types.Snapshot(
        description=SNAPSHOT_DESC_1,
        persist_memorystate=False,
        disk_attachments=[
            types.DiskAttachment(
                disk=types.Disk(
                    id=disk.id
                )
            )
        ]
    )

    snapshots_service.add(dead_snap1_params)

    testlib.assert_true_within_long(
        lambda:
        snapshots_service.list()[-1].snapshot_status == types.SnapshotStatus.OK
    )

    dead_snap2_params = types.Snapshot(
        description=SNAPSHOT_DESC_2,
        persist_memorystate=False,
        disk_attachments=[
            types.DiskAttachment(
                disk=types.Disk(
                    id=disk.id
                )
            )
        ]
    )

    snapshots_service.add(dead_snap2_params)

    testlib.assert_true_within_long(
        lambda:
        snapshots_service.list()[-1].snapshot_status == types.SnapshotStatus.OK
    )

    snapshot = snapshots_service.list()[-2]
    snapshots_service.snapshot_service(snapshot.id).remove()

    testlib.assert_true_within_long(
        lambda:
        (len(snapshots_service.list()) == 2) and
        (
            snapshots_service.list()[-1].snapshot_status == (
                types.SnapshotStatus.OK
            )
        ),
    )


@testlib.with_ovirt_api4
def cold_storage_migration(api):
    disk_service = _get_disk_service(api.system_service(), DISK2_NAME)

    # Cold migrate the disk to ISCSI storage domain and then migrate it back
    # to the NFS domain because it is used by other cases that assume the
    # disk found on that specific domain
    for domain in [SD_ISCSI_NAME, SD_SECOND_NFS_NAME]:
        disk_service.move(
            async=False,
            storage_domain=types.StorageDomain(
                name=domain
            )
        )

        testlib.assert_true_within_long(
            lambda: api.follow_link(
                disk_service.get().storage_domains[0]
            ).name == domain and (
                disk_service.get().status == types.DiskStatus.OK
            )
        )


@testlib.with_ovirt_api4
def live_storage_migration(api):
    engine = api.system_service()
    vm_service = _get_vm_service(engine, VM0_NAME)
    disk_service = _get_disk_service(engine, DISK0_NAME)
    disk_service.move(
        async=False,
        filter=False,
        storage_domain=types.StorageDomain(
            name=SD_ISCSI_NAME
        )
    )

    snapshots_service = vm_service.snapshots_service()
    # Assert that the disk is on the correct storage domain,
    # its status is OK and the snapshot created for the migration
    # has been merged
    testlib.assert_equals_within_long(
        lambda: api.follow_link(disk_service.get().storage_domains[0]).name == SD_ISCSI_NAME and \
                len(snapshots_service.list()) == 1 and \
                disk_service.get().status, types.DiskStatus.OK)

    # This sleep is a temporary solution to the race condition
    # https://bugzilla.redhat.com/1456504
    time.sleep(3)


@testlib.with_ovirt_api4
def export_vm(api):
    engine = api.system_service()
    vm_service = _get_vm_service(engine, VM1_NAME)
    sd = engine.storage_domains_service().list(search=SD_TEMPLATES_NAME)[0]

    vm_service.export(
        storage_domain=types.StorageDomain(
            id=sd.id,
        ), discard_snapshots=True, async=True
    )


@testlib.with_ovirt_api4
def verify_vm_exported(api):
    engine = api.system_service()
    storage_domain_service = _get_storage_domain_service(engine, SD_TEMPLATES_NAME)

    testlib.assert_true_within_short(
        lambda:
        _get_storage_domain_vm_service_by_name(
            storage_domain_service, VM1_NAME
        ).get().status == types.VmStatus.DOWN
    )


@testlib.with_ovirt_api
def add_vm_template(api):
    #TODO: Fix the exported domain generation.
    #For the time being, add VM from Glance imported template.
    if api.templates.get(name=TEMPLATE_CIRROS) is None:
        raise SkipTest('%s: template %s not available.' % (add_vm_template.__name__, TEMPLATE_CIRROS))

    vm_memory = 512 * MB
    vm_params = params.VM(
        name=VM1_NAME,
        description='CirrOS imported from Glance as Template',
        memory=vm_memory,
        cluster=params.Cluster(
            name=TEST_CLUSTER,
        ),
        template=params.Template(
            name=TEMPLATE_CIRROS,
        ),
        use_latest_template_version=True,
        stateless=True,
        display=params.Display(
            type_='vnc',
        ),
        memory_policy=params.MemoryPolicy(
            guaranteed=vm_memory / 2,
            ballooning=False,
        ),
        os=params.OperatingSystem(
            type_='other_linux',
        ),
        timezone='Etc/GMT',
        type_='server',
        serial_number=params.SerialNumber(
            policy='custom',
            value='12345678',
        ),
        cpu=params.CPU(
            architecture='X86_64',
            topology=params.CpuTopology(
                cores=1,
                threads=2,
                sockets=1,
            ),
        ),
    )
    api.vms.add(vm_params)


@testlib.with_ovirt_api
def verify_add_vm_template(api):
    testlib.assert_true_within_long(
        lambda: api.vms.get(VM1_NAME).status.state == 'down',
    )
    vm = api.vms.get(VM1_NAME)
    disk_name = vm.disks.list()[0].name
    testlib.assert_true_within_long(
        lambda:
        vm.disks.get(disk_name).status.state == 'ok'
    )


@testlib.with_ovirt_api4
def add_filter(ovirt_api4):
    engine = ovirt_api4.system_service()
    nics_service = _get_nics_service(engine)
    nic = nics_service.list()[0]
    network = ovirt_api4.follow_link(nic.vnic_profile).network
    network_filters_service = engine.network_filters_service()
    network_filter = next(
        network_filter for network_filter in network_filters_service.list()
        if network_filter.name == NETWORK_FILTER_NAME
    )
    vnic_profiles_service = engine.vnic_profiles_service()

    vnic_profile = vnic_profiles_service.add(
        types.VnicProfile(
            name='{}_profile'.format(network_filter.name),
            network=network,
            network_filter=network_filter
        )
    )
    nic.vnic_profile = vnic_profile
    nt.assert_true(
        nics_service.nic_service(nic.id).update(nic)
    )


@testlib.with_ovirt_prefix
def add_filter_parameter(prefix):
    engine = prefix.virt_env.engine_vm()
    ovirt_api4 = engine.get_api(api_ver=4)
    vm_gw = '.'.join(engine.ip().split('.')[0:3] + ['1'])
    network_filter_parameters_service = _get_network_fiter_parameters_service(
        ovirt_api4.system_service())

    nt.assert_true(
        network_filter_parameters_service.add(
            types.NetworkFilterParameter(
                name=NETWORK_FILTER_PARAMETER0_NAME,
                value=NETWORK_FILTER_PARAMETER0_VALUE
            )
        )
    )

    nt.assert_true(
        network_filter_parameters_service.add(
            types.NetworkFilterParameter(
                name=NETWORK_FILTER_PARAMETER1_NAME,
                value=vm_gw
            )
        )
    )

@testlib.with_ovirt_prefix
def vm_run(prefix):
    engine = prefix.virt_env.engine_vm()
    api = engine.get_api()
    vm_ip = '.'.join(engine.ip().split('.')[0:3] + ['199'])
    vm_gw = '.'.join(engine.ip().split('.')[0:3] + ['1'])
    host_names = [h.name() for h in prefix.virt_env.host_vms()]

    start_params = params.Action(
        use_cloud_init=True,
        vm=params.VM(
            placement_policy=params.VmPlacementPolicy(
                host=params.Host(
                    name=sorted(host_names)[0]
                ),
            ),
            initialization=params.Initialization(
                domain=params.Domain(
                    name='lago.example.com'
                ),
                cloud_init=params.CloudInit(
                    host=params.Host(
                        address='VM0'
                    ),
                    users=params.Users(
                        active=True,
                        user=[params.User(
                            user_name='root',
                            password='secret'
                        )]
                    ),
                    network_configuration=params.NetworkConfiguration(
                        nics=params.Nics(
                            nic=[params.NIC(
                                name='eth0',
                                boot_protocol='STATIC',
                                on_boot=True,
                                network=params.Network(
                                    ip=params.IP(
                                        address=vm_ip,
                                        netmask='255.255.255.0',
                                        gateway=vm_gw,
                                    ),
                                ),
                            )]
                        ),
                    ),
                ),
            ),
        ),
    )
    api.vms.get(VM0_NAME).start(start_params)
    start_params.vm.initialization.cloud_init=params.CloudInit(
        host=params.Host(
            address='VM2'
        ),
    )
    api.vms.get(VM2_NAME).start(start_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM0_NAME).status.state == 'up',
    )
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM2_NAME).status.state == 'up',
    )


@testlib.with_ovirt_prefix
def ping_vm0(ovirt_prefix):
    nt.assert_equals(_ping(ovirt_prefix, VM0_PING_DEST), EX_OK)


@testlib.with_ovirt_prefix
def ha_recovery(prefix):
    engine = prefix.virt_env.engine_vm().get_api_v4().system_service()
    last_event = int(engine.events_service().list(max=2)[0].id)
    vms_service = engine.vms_service()
    vm = vms_service.list(search=VM2_NAME)[0]
    host_name = engine.hosts_service().host_service(vm.host.id).get().name
    vm_host = prefix.virt_env.get_vm(host_name)
    pid = vm_host.ssh(['pgrep', '-f', 'qemu.*guest=vm2'])
    vm_host.ssh(['kill', '-KILL', pid.out])
    events = engine.events_service()
    testlib.assert_true_within_short(
        lambda:
        (next(e for e in events.list(from_=last_event) if e.code == 9602)).code == 9602,
         allowed_exceptions=[StopIteration]
    )
    vm_service = vms_service.vm_service(vm.id)
    testlib.assert_true_within_long(
        lambda:
        vm_service.get().status == types.VmStatus.UP
    )
    vm_service.stop()


@testlib.with_ovirt_prefix
def vdsm_recovery(prefix):
    api = prefix.virt_env.engine_vm().get_api()
    host_id = api.vms.get(VM0_NAME).host.id
    vm_host_name = api.hosts.get(id=host_id).name
    hosts = prefix.virt_env.host_vms()
    vm_host = next(h for h in hosts if h.name() == vm_host_name)
    vm_host.service('vdsmd').stop()
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM0_NAME).status.state == 'unknown',
    )
    vm_host.service('vdsmd').start()
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM0_NAME).status.state == 'up',
    )


@testlib.with_ovirt_api4
def template_export(api):
    templates_service = api.system_service().templates_service()
    template_cirros = templates_service.template_service(templates_service.list(search=TEMPLATE_CIRROS)[0].id)

    if template_cirros is None:
        raise SkipTest('{0}: template {1} is missing'.format(
            template_export.__name__,
            TEMPLATE_CIRROS
            )
        )

    storage_domain = api.system_service().storage_domains_service().list(search=SD_TEMPLATES_NAME)[0]
    template_cirros.export(
        storage_domain=types.StorageDomain(
            id=storage_domain.id,
        ),
    )
    template_id = template_cirros.get().id
    template_service = templates_service.template_service(template_id)
    testlib.assert_true_within_long(
        lambda:
        template_service.get().status == types.TemplateStatus.OK,
    )


@testlib.with_ovirt_api4
def add_vm_pool(api):
    engine = api.system_service()
    pools_service = engine.vm_pools_service()
    pool_cluster = engine.clusters_service().list(search=TEST_CLUSTER)[0]
    pool_template = engine.templates_service().list(search=TEMPLATE_CIRROS)[0]
    pools_service.add(
        pool=types.VmPool(
            name=VMPOOL_NAME,
            cluster=pool_cluster,
            template=pool_template,
            use_latest_template_version=True,
        )
    )
    vms_service = engine.vms_service()
    testlib.assert_true_within_short(
        lambda:
        vms_service.list(search=VMPOOL_NAME+'-1')[0].status == types.VmStatus.DOWN,
        allowed_exceptions=[IndexError]
    )


@testlib.with_ovirt_api4
def update_template_version(api):
    engine = api.system_service()
    vms_service = engine.vms_service()
    stateless_vm = vms_service.list(search=VM1_NAME)[0]
    templates_service = engine.templates_service()
    template = templates_service.list(search=TEMPLATE_CIRROS)[0]

    nt.assert_true(stateless_vm.memory != template.memory)

    templates_service.add(
        template=types.Template(
            name=TEMPLATE_CIRROS,
            vm=stateless_vm,
            version=types.TemplateVersion(
                base_template=template,
                version_number=2
            )
        )
    )
    pools_service = engine.vm_pools_service()
    testlib.assert_true_within_long(
        lambda:
        pools_service.list(search=VMPOOL_NAME)[0].vm.memory == stateless_vm.memory
    )


@testlib.with_ovirt_api4
def update_vm_pool(api):
    vm_pools_service= api.system_service().vm_pools_service()
    pool_id = vm_pools_service.list(search=VMPOOL_NAME)[0].id
    vm_pools_service.pool_service(id=pool_id).update(
        pool=types.VmPool(
            max_user_vms=2
        )
    )
    nt.assert_true(
        vm_pools_service.list(search=VMPOOL_NAME)[0].max_user_vms == 2
    )


@testlib.with_ovirt_api4
def remove_vm_pool(api):
    vm_pools_service = api.system_service().vm_pools_service()
    pool_id = vm_pools_service.list(search=VMPOOL_NAME)[0].id
    vm_pools_service.pool_service(id=pool_id).remove()
    nt.assert_true(
         len(vm_pools_service.list()) == 0
    )


@testlib.with_ovirt_api4
def template_update(api):
    templates_service = api.system_service().templates_service()
    template_cirros = templates_service.template_service(templates_service.list(search=TEMPLATE_CIRROS)[0].id)

    if template_cirros is None:
        raise SkipTest('{0}: template {1} is missing'.format(
            template_update.__name__,
            TEMPLATE_CIRROS
        )
    )
    new_comment = "comment by ovirt-system-tests"
    template_cirros.update(
        template = types.Template(
            comment=new_comment
        )
    )
    template_id = template_cirros.get().id
    template_service = templates_service.template_service(template_id)
    testlib.assert_true_within_short(
        lambda:
        template_service.get().status == types.TemplateStatus.OK
    )
    nt.assert_true(templates_service.list(search=TEMPLATE_CIRROS)[0].comment == new_comment)


@testlib.with_ovirt_api4
def disk_operations(api):
    vt = utils.VectorThread(
        [
            functools.partial(live_storage_migration),
            functools.partial(cold_storage_migration),
            functools.partial(snapshot_cold_merge),
        ],
    )
    vt.start_all()
    vt.join_all()


@testlib.with_ovirt_api4
def hotplug_memory(api):
    engine = api.system_service()
    vms_service = engine.vms_service()
    vm_service = _get_vm_service(engine, VM0_NAME)
    new_memory = vm_service.get().memory * 2
    vm_service.update(
        vm=types.Vm(
            memory=new_memory
        )
    )
    nt.assert_true(
        vms_service.list(search=VM0_NAME)[0].memory == new_memory
    )


@testlib.with_ovirt_api4
def hotplug_cpu(api):
    engine = api.system_service()
    vms_service = engine.vms_service()
    vm_service = _get_vm_service(engine, VM0_NAME)
    new_cpu = vm_service.get().cpu
    new_cpu.topology.sockets = 2
    vm_service.update(
        vm=types.Vm(
            cpu=new_cpu
        )
    )
    nt.assert_true(
        vms_service.list(search=VM0_NAME)[0].cpu.topology.sockets == 2
    )

@testlib.with_ovirt_api4
def next_run_unplug_cpu(api):
    engine = api.system_service()
    vms_service = engine.vms_service()
    vm_service = _get_vm_service(engine, VM0_NAME)
    new_cpu = vm_service.get().cpu
    new_cpu.topology.sockets = 1
    vm_service.update(
        vm=types.Vm(
            cpu=new_cpu,
        ),
        next_run=True
    )
    nt.assert_true(
        vms_service.list(search=VM0_NAME)[0].cpu.topology.sockets == 2
    )
    nt.assert_true(
        vm_service.get(next_run=True).cpu.topology.sockets == 1
    )
    vm_service.reboot()
    testlib.assert_true_within_long(
        lambda:
         vms_service.list(search=VM0_NAME)[0].status == types.VmStatus.UP
    )
    nt.assert_true(
        vms_service.list(search=VM0_NAME)[0].cpu.topology.sockets == 1
    )


@testlib.with_ovirt_api
def hotplug_nic(api):
    nic2_params = params.NIC(
        name='eth1',
        network=params.Network(
            name=VM_NETWORK,
        ),
        interface='virtio',
    )
    api.vms.get(VM0_NAME).nics.add(nic2_params)


@testlib.with_ovirt_api4
def hotplug_disk(api):
    vm_service = _get_vm_service(api.system_service(), VM0_NAME)
    disk_attachments_service = vm_service.disk_attachments_service()
    disk_attachment = disk_attachments_service.add(
        types.DiskAttachment(
            disk=types.Disk(
                name=DISK0_NAME,
                provisioned_size=2 * GB,
                format=types.DiskFormat.COW,
                storage_domains=[
                    types.StorageDomain(
                        name=SD_NFS_NAME,
                    ),
                ],
                status=None,
                sparse=True,
            ),
            interface=types.DiskInterface.VIRTIO,
            bootable=False,
            active=True
        )
    )

    disks_service = api.system_service().disks_service()
    disk_service = disks_service.disk_service(disk_attachment.disk.id)
    attachment_service = disk_attachments_service.attachment_service(disk_attachment.id)

    testlib.assert_true_within_short(
        lambda:
        attachment_service.get().active and
        disk_service.get().status == types.DiskStatus.OK
    )


@testlib.with_ovirt_api4
def hotunplug_disk(api):
    engine = api.system_service()
    vm_service = _get_vm_service(engine, VM0_NAME)
    disk_service = _get_disk_service(engine, DISK0_NAME)
    disk_attachments_service = vm_service.disk_attachments_service()
    disk_attachment = disk_attachments_service.attachment_service(disk_service.get().id)

    nt.assert_true(
        disk_attachment.update(types.DiskAttachment(active=False))
    )

    testlib.assert_true_within_short(
        lambda:
        disk_attachment.get().active == False
    )


@testlib.with_ovirt_api
def suspend_resume_vm(api):
    nt.assert_true(api.vms.get(VM0_NAME).suspend())

    testlib.assert_true_within_long(
        lambda:
        api.vms.get(VM0_NAME).status.state == 'suspended'
    )

    nt.assert_true(api.vms.get(VM0_NAME).start())


@testlib.with_ovirt_api
def verify_suspend_resume_vm(api):
    testlib.assert_true_within_long(
        lambda:
        api.vms.get(VM0_NAME).status.state == 'up'
    )


@testlib.with_ovirt_api
def add_event(api):
    event_params = params.Event(
        description='ovirt-system-tests description',
        custom_id=int('01234567890'),
        severity='NORMAL',
        origin='ovirt-system-tests',
        cluster=params.Cluster(
            name=TEST_CLUSTER,
        ),
    )

    nt.assert_true(api.events.add(event_params))


_TEST_LIST = [
    add_vm_blank,
    add_vm_template,
    add_nic,
    add_console,
    add_directlun,
    add_filter,
    add_filter_parameter,
    verify_add_vm_template,
    add_disk,
    export_vm,
    vm_run,
    ping_vm0,
    suspend_resume_vm,
    verify_vm_exported,
    ha_recovery,
    add_event,
    template_export,
    template_update,
    verify_suspend_resume_vm,
    hotplug_memory,
    hotplug_cpu,
    next_run_unplug_cpu,
    hotplug_disk,
    disk_operations,
    hotplug_nic,
    hotunplug_disk,
    add_vm_pool,
    update_template_version,
    update_vm_pool,
    remove_vm_pool,
    vdsm_recovery
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
