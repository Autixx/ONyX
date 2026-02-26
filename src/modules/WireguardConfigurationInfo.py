from pydantic import BaseModel, Field

class OverridePeerSettingsClass(BaseModel):
    DNS: str = ''
    EndpointAllowedIPs: str = ''
    MTU: str | int = ''
    PersistentKeepalive: int | str = ''
    PeerRemoteEndpoint: str = ''
    ListenPort: int | str = ''
    
class PeerGroupsClass(BaseModel):
    GroupName: str = ''
    Description: str = ''
    BackgroundColor: str = ''
    Icon: str = ''
    Peers: list[str] = Field(default_factory=list)

class MultiHopConfigurationClass(BaseModel):
    Enabled: bool = False
    OutboundInterface: str = ''
    OutboundGateway: str = ''
    RoutedNetworks: str = '0.0.0.0/0'
    ExcludedNetworks: str = ''
    TableID: int | str = 51820
    RulePriority: int | str = 10000
    FirewallMark: int | str = 51820
    EnableMasquerade: bool = True
    AutoSetInterfaceTableOff: bool = True
    GeoDirectEnabled: bool = False
    GeoDirectCountries: str = ''
    GeoDirectSourceTemplate: str = 'https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone'
    GeoZoneRules: list[dict[str, str]] = Field(default_factory=list)
    LocalDNSInstalled: bool = False
    LocalDNSAddress: str = ''

class WireguardConfigurationInfo(BaseModel):
    Description: str = ''
    OverridePeerSettings: OverridePeerSettingsClass = Field(default_factory=OverridePeerSettingsClass)
    PeerGroups: dict[str, PeerGroupsClass] = Field(default_factory=dict)
    PeerTrafficTracking: bool = True
    PeerHistoricalEndpointTracking: bool = True
    MultiHop: MultiHopConfigurationClass = Field(default_factory=MultiHopConfigurationClass)
