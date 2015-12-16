"""
    picasso.io
    ~~~~~~~~~~

    General purpose library for handling input and output of files

    :author: Joerg Schnitzbauer, 2015
"""


import os.path as _ospath
import numpy as _np
import yaml as _yaml
import tifffile as _tifffile
import glob as _glob
import h5py as _h5py
import re as _re


class FileFormatNotSupported(Exception):
    pass


def to_little_endian(movie, info):
    movie = movie.byteswap()
    info['Byte Order'] = '<'
    return movie, info


def load_raw(path, memory_map=True):
    info = load_info(path)
    info = info[0]
    dtype = _np.dtype(info['Data Type'])
    shape = (info['Frames'], info['Height'], info['Width'])
    if memory_map:
        movie = _np.memmap(path, dtype, 'r', shape=shape)
    else:
        movie = _np.fromfile(path, dtype)
        movie = _np.reshape(movie, shape)
    if info['Byte Order'] != '<':
        movie, info = to_little_endian(movie, info)
    return movie, info


def load_info(path):
    path_base, path_extension = _ospath.splitext(path)
    with open(path_base + '.yaml', 'r') as info_file:
        info = list(_yaml.load_all(info_file))
    return info


def save_info(path, info):
    with open(path, 'w') as file:
        _yaml.dump_all(info, file, default_flow_style=False)


def load_tif(path):
    info = {}
    with _tifffile.TiffFile(path) as tif:
        movie = tif.asarray(memmap=True)
        info = {}
        info['Byte Order'] = tif.byteorder
        info['Data Type'] = _np.dtype(tif.pages[0].dtype).name
        info['File'] = tif.filename
        info['Frames'], info['Height'], info['Width'] = movie.shape
        try:
            info['Comments'] = tif.micromanager_metadata['comments']['Summary']
            info['Computer'] = tif.micromanager_metadata['summary']['ComputerName']
            info['Directory'] = tif.micromanager_metadata['summary']['Directory']
            micromanager_metadata = tif.pages[0].tags['micromanager_metadata'].value
            info['Camera'] = {'Manufacturer': micromanager_metadata['Camera']}
            if info['Camera']['Manufacturer'] == 'Andor':
                _, type, model, serial_number, _ = (_.strip() for _ in micromanager_metadata['Andor-Camera'].split('|'))
                info['Camera']['Type'] = type
                info['Camera']['Model'] = model
                info['Camera']['Serial Number'] = int(serial_number)
                info['Output Amplifier'] = 'Electron Multiplying'
                if micromanager_metadata['Andor-EMSwitch'] == 'Off':
                    info['Output Amplifier'] = 'Conventional'
                info['EM RealGain'] = int(micromanager_metadata['Andor-Gain'])
                info['Pre-Amp Gain'] = int(micromanager_metadata['Andor-Pre-Amp-Gain'].split()[1])
                info['Readout Mode'] = micromanager_metadata['Andor-ReadoutMode']
            info['Excitation Wavelength'] = int(micromanager_metadata['TIFilterBlock1-Label'][-3:])
        except Exception as error:
            print('Exception in io.load_tif:')
            print(error)
    return movie, info


def _to_raw_single(path):
    path_base, path_extension = _ospath.splitext(path)
    path_extension = path_extension.lower()
    if path_extension in ['.tif', '.tiff']:
        movie, info = load_tif(path)
    else:
        raise FileFormatNotSupported("File format must be '.tif' or '.tiff'.")
    raw_file_name = path_base + '.raw'
    if info['Byte Order'] != '<':
        movie, info = to_little_endian(movie, info)     # Numpy default is little endian, Numba does not work with big endian
    movie.tofile(raw_file_name)
    info['Generated by'] = 'Picasso ToRaw'
    info['Original File'] = info.pop('File')
    info['File'] = _ospath.basename(raw_file_name)
    with open(path_base + '.yaml', 'w') as info_file:
        _yaml.safe_dump(info, info_file)


def to_raw_combined(paths):
    path_base, path_extension = _ospath.splitext(paths[0])
    path_extension = path_extension.lower()
    raw_file_name = path_base + '.raw'
    with open(raw_file_name, 'wb') as file_handle:
        movie, info = load_tif(paths[0])
        if info['Byte Order'] == '>':
            movie, info = to_little_endian(movie, info)
        movie.tofile(file_handle)
        for path in paths[1:]:
            movie, info_single = load_tif(paths[0])
            if info_single['Byte Order'] == '>':
                movie, info = to_little_endian(movie, info)
            movie.tofile(file_handle)
    info['Generated by'] = 'Picasso ToRaw'
    info['Original File'] = info.pop('File')
    info['File'] = _ospath.basename(raw_file_name)
    with open(path_base + '.yaml', 'w') as info_file:
        _yaml.safe_dump(info, info_file)


def get_movie_groups(paths):
    groups = []
    paths = paths.copy()
    while len(paths) > 0:
        path = paths[0]
        if path.endswith('.ome.tif'):
            path_base = path[0:-8]
            pattern = r'{}'.format(path_base + '_([0-9]).ome.tif')
            matches = [_re.match(pattern, _) for _ in paths]
            group = [path] + [_.group() for _ in matches if _]
            groups.append(group)
            for path_done in group:
                paths.remove(path_done)
    return groups


def to_raw(path, verbose=True):
    paths = _glob.glob(path)
    paths = [path.replace('\\', '/') for path in paths]
    groups = get_movie_groups(paths)
    n_groups = len(groups)
    if n_groups:
        for i, group in enumerate(groups):
            if verbose:
                print('Converting movie {}/{}...'.format(i + 1, n_groups), end='\r')
            to_raw_combined(group)
    else:
        if verbose:
            print('No files matching {}'.format(path))


def save_locs(path, locs, info):
    with _h5py.File(path, 'w') as locs_file:
        locs_file.create_dataset('locs', data=locs)
    base, ext = _ospath.splitext(path)
    info_path = base + '.yaml'
    save_info(info_path, info)


def load_locs(path):
    with _h5py.File(path, 'r') as locs_file:
        locs = locs_file['locs'][...]
    locs = _np.rec.array(locs, dtype=locs.dtype)    # Convert to rec array with fields as attributes
    info = load_info(path)
    return locs, info
