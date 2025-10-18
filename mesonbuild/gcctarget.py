from dataclasses import dataclass
from collections import OrderedDict

import os
import uuid
import pickle
import re
import shutil

from typing import Self
import typing as T

from . import build
from . import environment
from .build import Target
from .arglist import CompilerArgs
from .mesonlib import (
    File
)

vcxproj_01: str = """<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">"""

vcxproj_02: str = """
  <ItemGroup Label="ProjectConfigurations">
    <ProjectConfiguration Include="Debug|ARM">
      <Configuration>Debug</Configuration>
      <Platform>ARM</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|ARM">
      <Configuration>Release</Configuration>
      <Platform>ARM</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Debug|ARM64">
      <Configuration>Debug</Configuration>
      <Platform>ARM64</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|ARM64">
      <Configuration>Release</Configuration>
      <Platform>ARM64</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Debug|x86">
      <Configuration>Debug</Configuration>
      <Platform>x86</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|x86">
      <Configuration>Release</Configuration>
      <Platform>x86</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Debug|x64">
      <Configuration>Debug</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|x64">
      <Configuration>Release</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
  </ItemGroup>
  <PropertyGroup Label="Globals">
    <ProjectGuid>{puid}</ProjectGuid>
    <Keyword>Linux</Keyword>
    <RootNamespace>{pname}</RootNamespace>
    <MinimumVisualStudioVersion>15.0</MinimumVisualStudioVersion>
    <ApplicationType>Linux</ApplicationType>
    <ApplicationTypeRevision>1.0</ApplicationTypeRevision>
    <TargetLinuxPlatform>Generic</TargetLinuxPlatform>
  </PropertyGroup>
  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.Default.props" />
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|ARM'" Label="Configuration">
    <UseDebugLibraries>true</UseDebugLibraries>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|ARM'" Label="Configuration">
    <UseDebugLibraries>false</UseDebugLibraries>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x86'" Label="Configuration">
    <UseDebugLibraries>true</UseDebugLibraries>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x86'" Label="Configuration">
    <UseDebugLibraries>false</UseDebugLibraries>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'" Label="Configuration">
    <UseDebugLibraries>true</UseDebugLibraries>{ct}
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'" Label="Configuration">
    <UseDebugLibraries>false</UseDebugLibraries>{ct}
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|ARM64'" Label="Configuration">
    <UseDebugLibraries>false</UseDebugLibraries>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|ARM64'" Label="Configuration">
    <UseDebugLibraries>true</UseDebugLibraries>
  </PropertyGroup>
  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.props" />
  <ImportGroup Label="ExtensionSettings" />
  <ImportGroup Label="Shared" />
  <ImportGroup Label="PropertySheets" />
  <PropertyGroup Label="UserMacros" />"""

vcxproj_98: str = """  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'">
    <ClCompile>
      <AdditionalIncludeDirectories>{}%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>
      <PreprocessorDefinitions>{}%(PreprocessorDefinitions)</PreprocessorDefinitions>
    </ClCompile>
  </ItemDefinitionGroup>"""

vcxproj_99: str = """  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.targets" />
  <ImportGroup Label="ExtensionTargets" />
</Project>"""

vcxproj_f00: str = """<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup>
    <Filter Include="소스 파일">
      <UniqueIdentifier>{4FC737F1-C7A5-4376-A066-2A32D752A2FF}</UniqueIdentifier>
      <Extensions>cpp;c;cc;cxx;c++;cppm;ixx;def;odl;idl;hpj;bat;asm;asmx</Extensions>
    </Filter>
    <Filter Include="헤더 파일">
      <UniqueIdentifier>{93995380-89BD-4b04-88EB-625FBE52EBFB}</UniqueIdentifier>
      <Extensions>h;hh;hpp;hxx;h++;hm;inl;inc;ipp;xsd</Extensions>
    </Filter>
    <Filter Include="리소스 파일">
      <UniqueIdentifier>{67DA6AB6-F800-4c08-8B7A-83BB121AAD01}</UniqueIdentifier>
      <Extensions>rc;ico;cur;bmp;dlg;rc2;rct;bin;rgs;gif;jpg;jpeg;jpe;resx;tiff;tif;png;wav;mfcribbon-ms</Extensions>
    </Filter>
  </ItemGroup>
</Project>"""

@dataclass(eq=False)
class GCTargetInfo:
    DTARGETPATH: str = ".deps/targets"
    def __init__(self, target: Target, name: str):
        self.target: Target = target
        self.targetname: str = name
        self.target_sources: T.MutableMapping[str, File] = None
        self.generated_sources: T.MutableMapping[str, File] = None
        self.transpiled_sources: T.List[str] = None
        self.compiled_sources: T.List[str] = None
        self.final_obj_list: T.List[str] = None
        self.generated_object_files: T.List[str] = None
        self.source2command: T.MutableMapping[str, CompilerArgs] = None
        self.linkcommand: CompilerArgs = None

    def generate_project(self, env: environment):
        t_name = self.targetname[0: len(self.targetname) - 2] if self.targetname.endswith(".a") else self.targetname
        # if t_name == "src_libvirt.so.0.10000.0":
        #     pass
        t_vcxpach = os.path.join(env.get_build_dir(), ".src", self.targetname)
        t_vcxproj = os.path.join(t_vcxpach, t_name + ".vcxproj")
        if not os.path.exists(t_vcxpach): os.makedirs(t_vcxpach)

        # link = self.linkcommand.compiler
        ConfigurationType: str = ""
        if isinstance(self.target, build.StaticLibrary):
            ConfigurationType = "\n    <ConfigurationType>StaticLibrary</ConfigurationType>"
        elif isinstance(self.target, build.SharedLibrary):
            ConfigurationType = "\n    <ConfigurationType>DynamicLibrary</ConfigurationType>"

        deplibs: T.List
        incslist: T.List
        defslist: T.List
        deplibs, incslist, defslist = self.incs_deps_check(env)

        h_list = []
        h_buld = []
        for obj_file in self.final_obj_list:
            _file = os.path.abspath(os.path.join(env.get_build_dir(), obj_file + ".d"))
            # print(_file)
            if not os.path.exists(_file): continue
            with open(_file, 'r', encoding='utf-8') as f:
                while True:
                    line = f.readline()
                    if not line: break
                    _files = line.strip().split(' ') # 줄 끝의 줄 바꿈 문자를 제거한다.
                    for r_file in _files:
                        if r_file == '\\': break

                        # 컴파일 대상에 포함되어 있으면 SKIP
                        if r_file in self.compiled_sources: continue
                        # if r_file in s_files: continue

                        # 대상 오브젝트 파일
                        if r_file.endswith('.o:'): continue

                        d_file = os.path.abspath(r_file)
                        if d_file.startswith(env.get_source_dir()):
                            if r_file not in h_list: h_list.append(r_file)
                        elif d_file.startswith(env.get_build_dir()):
                            if r_file not in h_buld: h_buld.append(r_file)
                        elif d_file.startswith('/usr/include/'): pass
                        elif d_file.startswith('/usr/lib/'): pass
                        else : print("  ====> h miss {}".format(r_file))

        s_list = []
        s_buld = []
        for r_file in sorted(self.compiled_sources):
            if self.source2command.get(r_file, None) is None: print("  {} ==> miss {}".format(r_file, s))
            d_file = os.path.abspath(r_file)
            if d_file.startswith(env.get_source_dir()):
                if r_file not in s_list: s_list.append(r_file)
            elif d_file.startswith(env.get_build_dir()):
                if r_file not in s_buld: s_buld.append(r_file)
            else : print("  ====> h miss {}".format(r_file))
            pass

        h_list.sort()
        h_buld.sort()
        s_list.sort()
        s_buld.sort()
        # 프로젝터 생성
        with open(t_vcxproj, 'w', encoding='utf-8') as f:
            f.write(vcxproj_01)
            f.write(vcxproj_02.format(puid="{" + str(uuid.uuid4()) + "}", pname=t_name, ct=ConfigurationType) + "\n")

            # 헤더 정보 포함
            f.write('  <ItemGroup>\n')
            for _file in h_buld:
                h_txt = os.path.abspath(_file)[len(env.get_build_dir()) + 1:]
                if h_txt.endswith(".o"): f.write('    <Object Include="{}" />\n'.format(".builds/.ins/" + h_txt))
                else: f.write('    <ClInclude Include="{}" />\n'.format(".builds/.ins/" + h_txt))
                if os.path.exists(_file):
                    destfile = os.path.join(t_vcxpach, ".builds/.ins", h_txt)
                    destdir = os.path.dirname(destfile)
                    if not os.path.exists(destdir): os.makedirs(destdir)
                    shutil.copy(_file, destfile)

            for _file in h_list:
                h_txt = os.path.abspath(_file)[len(env.get_source_dir()) + 1:]
                if h_txt.endswith(".o"): f.write('    <Object Include="{}" />\n'.format(h_txt))
                else: f.write('    <ClInclude Include="{}" />\n'.format(h_txt))
                if os.path.exists(_file):
                    destfile = os.path.join(t_vcxpach, h_txt)
                    destdir = os.path.dirname(destfile)
                    if not os.path.exists(destdir): os.makedirs(destdir)
                    shutil.copy(_file, destfile)
            f.write('  </ItemGroup>\n')
            
            # 헤더 정보 포함
            f.write('  <ItemGroup>\n')
            for _file in s_buld:
                h_txt = os.path.abspath(_file)[len(env.get_build_dir()) + 1:]
                f.write('    <ClCompile Include="{}" />\n'.format(".builds/" + h_txt))
                if os.path.exists(_file):
                    destfile = os.path.join(t_vcxpach, ".builds", h_txt)
                    destdir = os.path.dirname(destfile)
                    if not os.path.exists(destdir): os.makedirs(destdir)
                    shutil.copy(_file, destfile)

            for _file in s_list:
                h_txt = os.path.abspath(_file)[len(env.get_source_dir()) + 1:]
                f.write('    <ClCompile Include="{}" />\n'.format(h_txt))
                if os.path.exists(_file):
                    destfile = os.path.join(t_vcxpach, h_txt)
                    destdir = os.path.dirname(destfile)
                    if not os.path.exists(destdir): os.makedirs(destdir)
                    shutil.copy(_file, destfile)
            f.write('  </ItemGroup>\n')

            f.write("""  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'">\n    <ClCompile>\n""")
            if len(incslist) > 0:
                f.write("      <AdditionalIncludeDirectories>{};%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>\n".format(";".join(incslist)))
            if len(defslist) > 0:
                f.write("      <PreprocessorDefinitions>{};%(PreprocessorDefinitions)</PreprocessorDefinitions>\n".format(";".join(defslist)))
            f.write("      <CLanguageStandard>gnu99</CLanguageStandard>\n")
            f.write("      <PositionIndependentCode>true</PositionIndependentCode>\n")
            f.write("    </ClCompile>\n")
            if len(deplibs) > 0:
              f.write('    <Link>\n')
              f.write("      <AdditionalDependencies>{};%(AdditionalDependencies)</AdditionalDependencies>\n".format(";".join(deplibs)))
              f.write('    </Link>\n')
            f.write("  </ItemDefinitionGroup>\n")
            f.write(vcxproj_99)
        
        # 필터 생성
        with open(t_vcxproj + ".filters", 'w', encoding='utf-8') as f:
            f.write(vcxproj_f00)

    def incs_deps_check(self, env: environment.Environment):
        deplibs = []
        incslist = []
        defslist = []
        c = self.linkcommand
        args = sorted([ t for t in set(list(c)[1:]) ])

        for item in args:
            if item.startswith('-L'):
                pass
                # if len(item) > 2:
                #     path = item[2:]
                # else:
                #     try:
                #         path = next(it)
                #     except StopIteration:
                #         mlog.warning("Generated linker command has -L argument without following path")
                #         break
                # if not os.path.isabs(path):
                #     path = os.path.join(build_dir, path)
                # search_dirs.add(path)
            elif item.startswith('-l'):
                pass
                # if len(item) > 2:
                #     lib = item[2:]
                # else:
                #     try:
                #         lib = next(it)
                #     except StopIteration:
                #         mlog.warning("Generated linker command has '-l' argument without following library name")
                #         break
                # libs.add(lib)
            elif item.startswith('-Wl,'):
                pass
            elif env.is_library(item) and os.path.isfile(item):
                deplibs.append(item)
        # print(deplibs)

        source2inx: T.MutableMapping[str, int] = OrderedDict()
        source2cnt: T.MutableMapping[str, int] = OrderedDict()
        keys = sorted([ s for s in self.source2command.keys() ])
        argid = {}
        for idx, k in enumerate(keys):
            _i = source2inx.get(k, None)
            if not _i is None: continue

            cnts: int = 1;
            source2inx[k] = idx
            c = self.source2command.get(k, None)
            if c is None: continue
            argid = { t for t in set(list(c)[1:]) if t.startswith(("-D", "-I")) }
            for s in keys[idx + 1: ]:
                _i = source2inx.get(s, None)
                if not _i is None: continue

                c = self.source2command.get(s, None)
                args = { t for t in set(list(c)[1:]) if t.startswith(("-D", "-I")) }
                if argid == args:
                    cnts += 1
                    source2inx[s] = idx
            source2cnt[k] = cnts

        if len(source2cnt) > 0:
            source2 = {k: v for k, v in sorted(source2cnt.items(), key=lambda item: item[1], reverse=True)}
            # print(source2)
            # my_dict = {'cherry': 1, 'apple': 2, 'banana': 3}
            # print({k: v for k, v in sorted(my_dict.items(), key=lambda item: item[1], reverse=True)})
            key = next(iter(source2))
            c = self.source2command.get(key, None)
            args = { t for t in set(list(c)[1:]) if t.startswith(("-D", "-I")) }
            for arg in args:
                incpath = arg[2:]
                if arg.startswith("-I"):
                    incpath = os.path.abspath(incpath)
                    if (incpath).startswith(env.get_build_dir()):
                        incpath = "./.builds/.ins/" + incpath[len(env.get_build_dir()) + 1:]
                        # if r_file not in s_list: s_list.append(r_file)
                    elif (incpath).startswith(env.get_source_dir()):
                        incpath = "./" + incpath[len(env.get_source_dir()) + 1:]
                    if incpath.endswith("/"): 
                        incpath = incpath[0: len(incpath) - 1]
                    incslist.append(incpath)
                if arg.startswith("-D"): defslist.append(incpath)
        return ( sorted(list(set(deplibs))), sorted(list(set(incslist))), sorted(list(set(defslist))) )

    def save(self, evn: environment.Environment):
        dep_path = os.path.join(evn.get_build_dir(), self.DTARGETPATH)
        if not os.path.exists(dep_path): os.makedirs(dep_path)
        with open(os.path.join(dep_path, self.targetname), 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def loadfrom(evn: environment.Environment, targetname) -> Self:
        dep_path = os.path.join(evn.get_build_dir(), GCTargetInfo.DTARGETPATH)
        with open(os.path.join(dep_path, targetname), 'rb') as f:
            obj = pickle.load(f)
        return obj