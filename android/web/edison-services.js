// Edison runs independently of the original game's services.
export const roomsUnavailable = 'Tag Duels, Draft Duels and Ultimate Collector are unavailable in this Edison build.';
export const cloudUnavailable = 'Cloud Save and Link Devices are unavailable. Progress is saved on this device.';
export const replaysUnavailable = 'Replay uploads and behaviour flags are unavailable. You can watch local replays in Run History.';
export const statsUnavailable = 'Worldwide and character statistics are unavailable. Device Stats still works.';

// The release has no Edison-owned Workers. Fail before reading credentials or making requests.
export const roomService = () => { throw Error(roomsUnavailable); };
export const replayService = () => { throw Error(replaysUnavailable); };
export const statsService = () => { throw Error(statsUnavailable); };
