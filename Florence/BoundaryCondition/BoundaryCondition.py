import numpy as np, scipy as sp, sys, os, gc
from warnings import warn
from time import time
# import scipy as sp
# from DirichletBoundaryDataFromCAD import IGAKitWrapper, PostMeshWrapper
# import numpy as np, sys, gc

from Florence.QuadratureRules import GaussLobattoQuadrature
from Florence.QuadratureRules.FeketePointsTri import FeketePointsTri
from Florence.QuadratureRules.EquallySpacedPoints import EquallySpacedPoints
import Florence.InterpolationFunctions.TwoDimensional.Tri.hpNodal as Tri

from Florence.MeshGeneration.CurvilinearMeshing.IGAKitPlugin.IdentifyNURBSBoundaries import GetDirichletData
# from Florence import PostMeshCurvePy as PostMeshCurve 
# from Florence import PostMeshSurfacePy as PostMeshSurface 


class BoundaryCondition(object):
    """Base class for applying all types of boundary conditions"""

    def __init__(self):
        # TYPE OF BOUNDARY straight OF nurbs
        self.boundary_type = 'straight'
        self.requires_cad = False
        self.cad_file = None
        # PROJECTION TYPE FOR CAD EITHER orthogonal OR arc_length
        self.projection_type = 'orthogonal'
        # WHAT TYPE OF ARC LENGTH BASED PROJECTION, EITHER 'equal' OR 'fekete'
        self.nodal_spacing_for_cad = 'equal'
        self.project_on_curves = False
        self.scale_mesh_on_projection = False
        self.scale_value_on_projection = 1.0
        self.condition_for_projection = 1.0e20
        self.has_planar_surfaces = False
        self.solve_for_planar_faces = True
        self.projection_flags = None
        # FIX DEGREES OF FREEDOM EVERY WHERE CAD PROJECTION IS NOT APPLIED 
        self.fix_dof_elsewhere = None
        # FOR 3D ARC-LENGTH PROJECTION
        self.orthogonal_fallback_tolerance = 1.0
        # WHICH ALGORITHM TO USE FOR SURFACE IDENTIFICATION, EITHER 'minimisation' or 'pure_projection'
        self.surface_identification_algorithm = 'minimisation'
        # MODIFY LINEAR MESH ON PROJECTION
        self.modify_linear_mesh_on_projection = 1

        # FOR IGAKit WRAPPER
        self.nurbs_info = None
        self.nurbs_condition = None

        self.analysis_type = 'static'
        self.analysis_nature = 'linear'

        self.is_dirichlet_computed = False
        self.columns_out = None
        self.columns_in = None
        self.applied_dirichlet = None


        # NODAL FORCES GENERATED BASED ON DIRICHLET OR NEUMANN ARE NOT 
        # IMPLEMENTED AS PART OF BOUNDARY CONDITION YET. THIS ESSENTIALLY
        # MEANS SAVING MULTIPLE RHS VALUES
        # self.dirichlet_forces = None
        # self.neumann_forces = None

        # # THE FOLLOWING MEMBERS ARE NOT UPDATED, TO REDUCE MEMORY FOOTPRINT 
        # self.external_nodal_forces = None
        # self.internal_traction_forces = None
        # self.residual = None


    def SetAnalysisParameters(self,analysis_type='static',analysis_nature='linear',
        columns_in=None,columns_out=None,applied_dirichlet=None):
        """Set analysis parameters such as analysis type, analysis nature and even
            Dirichlet boundary conditions if known a priori
        """
        self.analysis_type = analysis_type
        self.analysis_nature = analysis_nature
        self.columns_out = columns_out
        self.columns_in = columns_in
        self.applied_dirichlet = applied_dirichlet



    def SetCADProjectionParameters(self, cad_file=None, requires_cad=True, projection_type='orthogonal', 
        nodal_spacing='equal', project_on_curves=False, has_planar_surfaces=False, solve_for_planar_faces=True, 
        scale=1.0,condition=1.0e20, projection_flags=None, fix_dof_elsewhere=True,
        orthogonal_fallback_tolerance=1.0, surface_identification_algorithm='minimisation',
        modify_linear_mesh_on_projection=True):
        """Set parameters for CAD projection in order to obtain dirichlet boundary
            conditinos
        """

        self.boundary_type = 'nurbs'
        self.requires_cad = requires_cad
        self.cad_file = cad_file
        self.projection_type = projection_type
        self.scale_mesh_on_projection = True
        self.scale_value_on_projection = 1.0*scale
        self.condition_for_projection = 1.0*condition
        self.project_on_curves = project_on_curves
        self.has_planar_surfaces = has_planar_surfaces
        self.solve_for_planar_faces = solve_for_planar_faces
        self.projection_flags = projection_flags
        self.fix_dof_elsewhere = fix_dof_elsewhere
        self.orthogonal_fallback_tolerance = orthogonal_fallback_tolerance
        self.surface_identification_algorithm = surface_identification_algorithm
        self.modify_linear_mesh_on_projection = modify_linear_mesh_on_projection

        self.project_on_curves = int(self.project_on_curves)
        self.modify_linear_mesh_on_projection = int(self.modify_linear_mesh_on_projection)


    def SetProjectionCriteria(self, proj_func,mesh, takes_self=False, **kwargs):
        """Factory function for setting projection criteria specific 
            to a problem

            input:
                func                [function] function that computes projection criteria
                mesh                [Mesh] an instance of mesh class
                **kwargs            optional keyword arguments 
        """

        if takes_self:
            self.projection_flags  = proj_func(mesh,self)
        else:
            self.projection_flags = proj_func(mesh)

        if isinstance(self.projection_flags,np.ndarray):
            if self.projection_flags.ndim==1:
                self.projection_flags.reshape(-1,1)
                ndim = mesh.InferSpatialDimension()
                if self.projection_flags.shape[0] != mesh.edges.shape[0] and ndim == 2:
                    raise ValueError("Projection flags are incorrect. "
                        "Ensure that your projection function returns an ndarray of shape (mesh.edges.shape[0],1)")
                elif self.projection_flags.shape[0] != mesh.faces.shape[0] and ndim == 3:
                    raise ValueError("Projection flags are incorrect. "
                        "Ensure that your projection function returns an ndarray of shape (mesh.faces.shape[0],1)")
        else:
            raise ValueError("Projection flags for CAD not set. "
                "Ensure that your projection function returns an ndarray")


    def GetProjectionCriteria(self,mesh):
        """Convenience method for computing projection flags, as many problems
        require this type of projection
        """

        if mesh.element_type == "tet":
            projection_faces = np.zeros((mesh.faces.shape[0],1),dtype=np.uint64)
            num = mesh.faces.shape[1]
            for iface in range(mesh.faces.shape[0]):
                x = np.sum(mesh.points[mesh.faces[iface,:],0])/num
                y = np.sum(mesh.points[mesh.faces[iface,:],1])/num
                z = np.sum(mesh.points[mesh.faces[iface,:],2])/num
                x *= self.scale_value_on_projection
                y *= self.scale_value_on_projection
                z *= self.scale_value_on_projection
                if np.sqrt(x*x+y*y+z*z)< self.condition_for_projection:
                    projection_faces[iface]=1

            self.projection_flags = projection_faces

        elif mesh.element_type == "tri":
            projection_edges = np.zeros((mesh.edges.shape[0],1),dtype=np.uint64)
            num = mesh.edges.shape[1]
            for iedge in range(mesh.edges.shape[0]):
                x = np.sum(mesh.points[mesh.edges[iedge,:],0])/num
                y = np.sum(mesh.points[mesh.edges[iedge,:],1])/num
                x *= self.scale_value_on_projection
                y *= self.scale_value_on_projection
                if np.sqrt(x*x+y*y)< self.condition_for_projection:
                    projection_edges[iedge,0]=1
            
            self.projection_flags = projection_edges


    def DirichletCriterion(self,DirichArgs):
        pass



    def GetDirichletBoundaryConditions(self,MainData,mesh,material):

        #######################################################
        nvar = MainData.nvar
        ndim = MainData.ndim

        # ColumnsOut = []; AppliedDirichlet = []
        self.columns_in, self.applied_dirichlet = [], []


        #----------------------------------------------------------------------------------------------------#
        #-------------------------------------- NURBS BASED SOLUTION ----------------------------------------#
        #----------------------------------------------------------------------------------------------------#
        if self.boundary_type == 'nurbs':

            tCAD = time()

            # IsHighOrder = getattr(MainData.MeshInfo,"IsHighOrder",False)
            IsHighOrder = mesh.IsHighOrder
            # IsDirichletComputed = getattr(MainData.BoundaryData,"IsDirichletComputed",None)

                
            IsHighOrder = False

            if IsHighOrder is False:

                if not self.is_dirichlet_computed:

                    # GET DIRICHLET BOUNDARY CONDITIONS BASED ON THE EXACT GEOMETRY FROM CAD
                    if self.requires_cad:
                        # CALL POSTMESH WRAPPER
                        nodesDBC, Dirichlet = self.PostMeshWrapper(MainData,mesh,material)
                    else:
                        # CALL IGAKIT WRAPPER
                        nodesDBC, Dirichlet = self.IGAKitWrapper(MainData,mesh)

                else:
                    # nodesDBC, Dirichlet = MainData.BoundaryData.nodesDBC, MainData.BoundaryData.Dirichlet
                    nodesDBC, Dirichlet = self.nodesDBC, self.Dirichlet                

                # tt = time()

                # ColumnsOut = []; AppliedDirichlet = []
                # nOfDBCnodes = nodesDBC.shape[0]
                # for inode in range(nOfDBCnodes):
                #     for i in range(nvar):
                #         ColumnsOut = np.append(ColumnsOut,nvar*nodesDBC[inode]+i)
                #         AppliedDirichlet = np.append(AppliedDirichlet,Dirichlet[inode,i])

                # print time() - tt
                # tt = time()
                # print np.repeat(nodesDBC[:,None],nvar,axis=1)
                # print nodesDBC
                self.columns_out = (np.repeat(nodesDBC,nvar,axis=1)*nvar +\
                 np.tile(np.arange(nvar)[None,:],nodesDBC.shape[0]).reshape(nodesDBC.shape[0],MainData.ndim)).ravel()
                self.applied_dirichlet = Dirichlet.ravel()
                # temp_1 = np.repeat(nodesDBC,nvar,axis=1)*nvar
                # temp_2 = np.tile(np.arange(nvar)[None,:],nodesDBC.shape[0]).reshape(nodesDBC.shape[0],2)
                # self.columns_out = (temp_1+temp_2).flatten()
                # del temp_1, temp_2
                # print time() - tt
                # print nodesDBC.shape
                # print self.columns_out.shape, ColumnsOut.shape
                # assert np.isclose(ColumnsOut.astype(np.int64) - self.columns_out,0.).all() 
                # assert np.isclose(self.applied_dirichlet - AppliedDirichlet,0.).all()
                # print AppliedDirichlet - self.applied_dirichlet
                # exit()

                # FIX THE DOF IN THE REST OF THE BOUNDARY
                if self.fix_dof_elsewhere:
                    if ndim==2:
                        Rest_DOFs = np.setdiff1d(np.unique(mesh.edges),nodesDBC)
                    elif ndim==3:
                        Rest_DOFs = np.setdiff1d(np.unique(mesh.faces),nodesDBC)
                    for inode in range(Rest_DOFs.shape[0]):
                        for i in range(nvar):
                            # ColumnsOut = np.append(ColumnsOut,nvar*Rest_DOFs[inode]+i)
                            # AppliedDirichlet = np.append(AppliedDirichlet,0.0)
                            self.columns_out = np.append(self.columns_out,nvar*Rest_DOFs[inode]+i)
                            self.applied_dirichlet = np.append(self.applied_dirichlet,0.0)

                print 'Finished identifying Dirichlet boundary conditions from CAD geometry. Time taken ', time()-tCAD, 'seconds'

                # end = -3
                # np.savetxt(MainData.MeshInfo.FileName.split(".")[0][:end]+"_Dirichlet_"+"P"+str(MainData.C+1)+".dat",AppliedDirichlet,fmt="%9.16f")
                # np.savetxt(MainData.MeshInfo.FileName.split(".")[0][:end]+"_ColumnsOut_"+"P"+str(MainData.C+1)+".dat",ColumnsOut)
                # # np.savetxt(MainData.MeshInfo.FileName.split(".")[0][:end]+"_PlanarMeshFaces_"+"P"+str(MainData.C+1)+".dat",MainData.planar_mesh_faces)

                # from scipy.io import savemat
                # print(MainData.MeshInfo.FileName.split(".")[0]+"_DirichletData_P"+str(MainData.C+1)+".mat")
                # Dict = {'AppliedDirichlet':AppliedDirichlet,'ColumnsOut':ColumnsOut.astype(np.int64)}
                # savemat(MainData.MeshInfo.FileName.split(".")[0]+"_DirichletData_P"+str(MainData.C+1)+".mat",Dict,do_compression=True)
                # # exit()

            else:
                
                end = -3
                self.applied_dirichlet = np.loadtxt(mesh.filename.split(".")[0][:end]+"_Dirichlet_"+"P"+str(MainData.C+1)+".dat",dtype=np.float64)
                self.columns_out = np.loadtxt(mesh.filename.split(".")[0][:end]+"_ColumnsOut_"+"P"+str(MainData.C+1)+".dat")

                # AppliedDirichlet = np.loadtxt("/home/roman/Dropbox/Florence/Examples/FiniteElements/Falcon3D/falcon_big_Dirichlet_P3.dat")
                # ColumnsOut = np.loadtxt("/home/roman/Dropbox/Florence/Examples/FiniteElements/Falcon3D/falcon_big_ColumnsOut_P3.dat")

                # AppliedDirichlet = np.loadtxt(MainData.DirichletName,dtype=np.float64)
                # ColumnsOut = np.loadtxt(MainData.ColumnsOutName)

                # AppliedDirichlet = AppliedDirichlet*MainData.CurrentIncr/MainData.nStep
                # AppliedDirichlet = AppliedDirichlet*1.0/MainData.nStep

                print 'Finished identifying Dirichlet boundary conditions from CAD geometry. Time taken ', time()-tCAD, 'seconds'



            ############################
            # print np.max(AppliedDirichlet), mesh.Bounds
            # exit()
            ############################

        #----------------------------------------------------------------------------------------------------#
        #------------------------------------- NON-NURBS BASED SOLUTION -------------------------------------#
        #----------------------------------------------------------------------------------------------------#

        elif self.boundary_type == 'straight' or self.boundary_type == 'mixed':
            # IF DIRICHLET BOUNDARY CONDITIONS ARE APPLIED DIRECTLY AT NODES
            if MainData.BoundaryData().DirichArgs.Applied_at == 'node':
                # GET UNIQUE NODES AT THE BOUNDARY
                unique_edge_nodes = []
                if ndim==2:
                    unique_edge_nodes = np.unique(mesh.edges)
                elif ndim==3:
                    unique_edge_nodes = np.unique(mesh.faces)
                # ACTIVATE THIS FOR DEBUGGING ELECTROMECHANICAL PROBLEMS
                # unique_edge_nodes = np.unique(mesh.elements) 


                MainData.BoundaryData().DirichArgs.points = mesh.points
                MainData.BoundaryData().DirichArgs.edges = mesh.edges
                for inode in range(0,unique_edge_nodes.shape[0]):
                    coord_node = mesh.points[unique_edge_nodes[inode]]
                    MainData.BoundaryData().DirichArgs.node = coord_node
                    MainData.BoundaryData().DirichArgs.inode = unique_edge_nodes[inode]

                    Dirichlet = MainData.BoundaryData().DirichletCriterion(MainData.BoundaryData().DirichArgs)

                    # COMMENTED RECENTLY IN FAVOR OF WHAT APPEARS BELOW
                    # if type(Dirichlet) is None:
                    #   pass
                    # else:
                    #   for i in range(nvar):
                    #       # if type(Dirichlet[i]) is list:
                    #       if Dirichlet[i] is None:
                    #           pass
                    #       else:
                    #           # ColumnsOut = np.append(ColumnsOut,nvar*inode+i) # THIS IS INVALID
                    #           # ACTIVATE THIS FOR DEBUGGING ELECTROMECHANICAL PROBLEMS
                    #           ColumnsOut = np.append(ColumnsOut,nvar*unique_edge_nodes[inode]+i)
                    #           AppliedDirichlet = np.append(AppliedDirichlet,Dirichlet[i])

                    if type(Dirichlet) is not None:
                        for i in range(nvar):
                            if Dirichlet[i] is not None:
                                # ColumnsOut = np.append(ColumnsOut,nvar*inode+i) # THIS IS INVALID
                                # ACTIVATE THIS FOR DEBUGGING ELECTROMECHANICAL PROBLEMS
                                ColumnsOut = np.append(ColumnsOut,nvar*unique_edge_nodes[inode]+i)
                                AppliedDirichlet = np.append(AppliedDirichlet,Dirichlet[i])


        # GENERAL PROCEDURE - GET REDUCED MATRICES FOR FINAL SOLUTION
        # ColumnsOut = ColumnsOut.astype(np.int64)
        # ColumnsIn = np.delete(np.arange(0,nvar*mesh.points.shape[0]),ColumnsOut)
        self.columns_out = self.columns_out.astype(np.int64)
        self.columns_in = np.delete(np.arange(0,nvar*mesh.points.shape[0]),self.columns_out)


        # return ColumnsIn, ColumnsOut, AppliedDirichlet



    def IGAKitWrapper(self,MainData,mesh):
        """Calls IGAKit wrapper to get exact Dirichlet boundary conditions"""

        # GET THE NURBS CURVE FROM PROBLEMDATA
        # nurbs = self.NURBSParameterisation()
        # IDENTIFIY DIRICHLET BOUNDARY CONDITIONS BASED ON THE EXACT GEOMETRY
        # nodesDBC, Dirichlet = GetDirichletData(mesh,nurbs,MainData.BoundaryData,MainData.C)
        C = mesh.InferPolynomialDegree() - 1
        nodesDBC, Dirichlet = GetDirichletData(mesh,self.nurbs_info,self,C) 

        return nodesDBC[:,None], Dirichlet



    def PostMeshWrapper(self,MainData,mesh,material):
        """Calls PostMesh wrapper to get exact Dirichlet boundary conditions"""

        from Florence import PostMeshCurvePy as PostMeshCurve 
        from Florence import PostMeshSurfacePy as PostMeshSurface 

        # GET BOUNDARY FEKETE POINTS
        if MainData.ndim == 2:
            
            # CHOOSE TYPE OF BOUNDARY SPACING 
            boundary_fekete = np.array([[]])
            # spacing_type = getattr(MainData.BoundaryData,'CurvilinearMeshNodalSpacing',None)
            # self.nodal_spacing
            if self.nodal_spacing_for_cad == 'fekete':
                boundary_fekete = GaussLobattoQuadrature(MainData.C+2)[0]
            else:
                boundary_fekete = EquallySpacedPoints(MainData.ndim,MainData.C)
            # IT IS IMPORTANT TO ENSURE THAT THE DATA IS C-CONITGUOUS
            boundary_fekete = boundary_fekete.copy(order="c")

            curvilinear_mesh = PostMeshCurve(mesh.element_type,dimension=MainData.ndim)
            curvilinear_mesh.SetMeshElements(mesh.elements)
            curvilinear_mesh.SetMeshPoints(mesh.points)
            curvilinear_mesh.SetMeshEdges(mesh.edges)
            curvilinear_mesh.SetMeshFaces(np.zeros((1,4),dtype=np.uint64))
            curvilinear_mesh.SetScale(self.scale_value_on_projection)
            curvilinear_mesh.SetCondition(self.condition_for_projection)
            curvilinear_mesh.SetProjectionPrecision(1.0e-04)
            # curvilinear_mesh.SetProjectionCriteria(MainData.BoundaryData().ProjectionCriteria(mesh))
            curvilinear_mesh.SetProjectionCriteria(self.projection_flags)
            curvilinear_mesh.ScaleMesh()
            # curvilinear_mesh.InferInterpolationPolynomialDegree() 
            curvilinear_mesh.SetNodalSpacing(boundary_fekete)
            curvilinear_mesh.GetBoundaryPointsOrder()
            # READ THE GEOMETRY FROM THE IGES FILE
            curvilinear_mesh.ReadIGES(self.cad_file)
            # EXTRACT GEOMETRY INFORMATION FROM THE IGES FILE
            geometry_points = curvilinear_mesh.GetGeomVertices()
            # print np.max(geometry_points[:,0]), mesh.Bounds
            # exit()
            curvilinear_mesh.GetGeomEdges()
            curvilinear_mesh.GetGeomFaces()

            curvilinear_mesh.GetGeomPointsOnCorrespondingEdges()
            # FIRST IDENTIFY WHICH CURVES CONTAIN WHICH EDGES
            curvilinear_mesh.IdentifyCurvesContainingEdges()
            # PROJECT ALL BOUNDARY POINTS FROM THE MESH TO THE CURVE
            curvilinear_mesh.ProjectMeshOnCurve()
            # FIX IMAGES AND ANTI IMAGES IN PERIODIC CURVES/SURFACES
            curvilinear_mesh.RepairDualProjectedParameters()
            # PERFORM POINT INVERSION FOR THE INTERIOR POINTS
            # projection_type = getattr(MainData.BoundaryData,'ProjectionType',None)
            if self.projection_type == 'orthogonal':
                curvilinear_mesh.MeshPointInversionCurve()
            elif self.projection_type == 'arc_length':
                curvilinear_mesh.MeshPointInversionCurveArcLength()
            else:
                print("projection type not understood. Arc length based projection is going to be used")
                curvilinear_mesh.MeshPointInversionCurveArcLength()
            # OBTAIN MODIFIED MESH POINTS - THIS IS NECESSARY TO ENSURE LINEAR MESH IS ALSO CORRECT
            curvilinear_mesh.ReturnModifiedMeshPoints(mesh.points)
            # GET DIRICHLET MainData
            nodesDBC, Dirichlet = curvilinear_mesh.GetDirichletData() 
            # FIND UNIQUE VALUES OF DIRICHLET DATA
            # posUnique = np.unique(nodesDBC,return_index=True)[1]
            # nodesDBC, Dirichlet = nodesDBC[posUnique], Dirichlet[posUnique,:]

            # GET ACTUAL CURVE POINTS - THIS FUNCTION IS EXPENSIVE
            # MainData.ActualCurve = curvilinear_mesh.DiscretiseCurves(100)

        elif MainData.ndim == 3:

            boundary_fekete = FeketePointsTri(MainData.C)

            curvilinear_mesh = PostMeshSurface(mesh.element_type,dimension=MainData.ndim)
            curvilinear_mesh.SetMeshElements(mesh.elements)
            curvilinear_mesh.SetMeshPoints(mesh.points)
            if mesh.edges.ndim == 2 and mesh.edges.shape[1]==0:
                mesh.edges = np.zeros((1,4),dtype=np.uint64)
            else:
                curvilinear_mesh.SetMeshEdges(mesh.edges)
            curvilinear_mesh.SetMeshFaces(mesh.faces)
            curvilinear_mesh.SetScale(self.scale_value_on_projection)
            curvilinear_mesh.SetCondition(self.condition_for_projection)
            curvilinear_mesh.SetProjectionPrecision(1.0e-04)
            curvilinear_mesh.SetProjectionCriteria(self.projection_flags)
            curvilinear_mesh.ScaleMesh()
            curvilinear_mesh.SetNodalSpacing(boundary_fekete)
            # curvilinear_mesh.GetBoundaryPointsOrder()
            # READ THE GEOMETRY FROM THE IGES FILE
            curvilinear_mesh.ReadIGES(self.cad_file)
            # EXTRACT GEOMETRY INFORMATION FROM THE IGES FILE
            geometry_points = curvilinear_mesh.GetGeomVertices()
            # print np.max(geometry_points[:,2]), mesh.Bounds
            # exit()
            curvilinear_mesh.GetGeomEdges()
            curvilinear_mesh.GetGeomFaces()
            print "CAD geometry has", curvilinear_mesh.NbPoints(), "points,", \
            curvilinear_mesh.NbCurves(), "curves and", curvilinear_mesh.NbSurfaces(), \
            "surfaces"
            curvilinear_mesh.GetGeomPointsOnCorrespondingFaces()

            # FIRST IDENTIFY WHICH SURFACES CONTAIN WHICH FACES
            # mesh.face_to_surface = None
            if getattr(mesh,"face_to_surface",None) is not None:
                if mesh.faces.shape[0] == mesh.face_to_surface.shape[0]:
                    curvilinear_mesh.SupplySurfacesContainingFaces(mesh.face_to_surface,already_mapped=1)
                else:
                    raise AssertionError("face-to-surface mapping does not seem correct. Point projection is going to stop")
            else:
                # curvilinear_mesh.IdentifySurfacesContainingFacesByPureProjection()
                curvilinear_mesh.IdentifySurfacesContainingFaces() 
            
            # IDENTIFY WHICH EDGES ARE SHARED BETWEEN SURFACES
            curvilinear_mesh.IdentifySurfacesIntersections()
            

            # PERFORM POINT INVERSION FOR THE INTERIOR POINTS
            Neval = np.zeros((3,boundary_fekete.shape[0]),dtype=np.float64)
            for i in range(3,boundary_fekete.shape[0]):
                Neval[:,i]  = Tri.hpBases(0,boundary_fekete[i,0],boundary_fekete[i,1],1)[0]
            # OrthTol = 0.5
            # project_on_curves = 0

            if self.projection_type == 'orthogonal':
                curvilinear_mesh.MeshPointInversionSurface(self.project_on_curves, self.modify_linear_mesh_on_projection)
            elif projection_type == 'arc_length':
                # PROJECT ALL BOUNDARY POINTS FROM THE MESH TO THE SURFACE
                curvilinear_mesh.ProjectMeshOnSurface()
                # curvilinear_mesh.RepairDualProjectedParameters()
                curvilinear_mesh.MeshPointInversionSurfaceArcLength(self.project_on_curves,
                    self.orthogonal_fallback_tolerance,Neval)
            else:
                warn("projection type not understood. Orthogonal projection is going to be used")
                curvilinear_mesh.MeshPointInversionSurface(self.project_on_curves)

            # OBTAIN MODIFIED MESH POINTS - THIS IS NECESSARY TO ENSURE LINEAR MESH IS ALSO CORRECT
            if self.modify_linear_mesh_on_projection:
                curvilinear_mesh.ReturnModifiedMeshPoints(mesh.points)
            # GET DIRICHLET DATA
            nodesDBC, Dirichlet = curvilinear_mesh.GetDirichletData()
            # GET DIRICHLET FACES (IF REQUIRED)
            dirichlet_faces = curvilinear_mesh.GetDirichletFaces()

            # np.savetxt("/home/roman/Dropbox/drill_log2",dirichlet_faces)
            # np.savetxt("/home/roman/Dropbox/valve_log2",dirichlet_faces)
            # np.savetxt("/home/roman/Dropbox/almond_log",dirichlet_faces)
            # np.savetxt("/home/roman/Dropbox/f6BL_log3",dirichlet_faces)
            # np.savetxt("/home/roman/Dropbox/f6_iso_log2",dirichlet_faces)

            # np.savetxt("/home/roman/Dropbox/almond_deb1",dirichlet_faces)
            # np.savetxt("/home/roman/Dropbox/almond_deb2",dirichlet_faces)        
            # exit()

            # # FIND UNIQUE VALUES OF DIRICHLET DATA
            # posUnique = np.unique(nodesDBC,return_index=True)[1]
            # nodesDBC, Dirichlet = nodesDBC[posUnique], Dirichlet[posUnique


            # FOR GEOMETRIES CONTAINING PLANAR SURFACES
            planar_mesh_faces = curvilinear_mesh.GetMeshFacesOnPlanarSurfaces()
            MainData.planar_mesh_faces = planar_mesh_faces

            # np.savetxt("/home/roman/Dropbox/nodesDBC_.dat",nodesDBC) 
            # np.savetxt("/home/roman/Dropbox/Dirichlet_.dat",Dirichlet)
            # np.savetxt("/home/roman/Dropbox/planar_mesh_faces_.dat",planar_mesh_faces)

            if self.solve_for_planar_faces:
                if planar_mesh_faces.shape[0] != 0:
                    # SOLVE A 2D PROBLEM FOR PLANAR SURFACES
                    switcher = MainData.Parallel
                    if MainData.Parallel is True or MainData.__PARALLEL__ is True:
                        MainData.Parallel = False
                        MainData.__PARALLEL__ = False

                    self.GetDirichletDataForPlanarFaces(MainData,material,mesh,planar_mesh_faces,nodesDBC,Dirichlet,plot=False)
                    MainData.__PARALLEL__ == switcher
                    MainData.Parallel = switcher

        return nodesDBC, Dirichlet


    @staticmethod
    def GetDirichletDataForPlanarFaces(MainData,material,mesh,planar_mesh_faces,nodesDBC,Dirichlet,plot=False):
        """Solve a 2D problem for planar faces. Modifies Dirichlet"""

        from Florence.Tensor import itemfreq, makezero
        from Florence import Mesh
        from Florence.FiniteElements.Solvers.Solver import MainSolver
        from Florence.FiniteElements.GetBasesAtInegrationPoints import GetBasesAtInegrationPoints
        from Florence.FiniteElements.PostProcess import PostProcess

        surface_flags = itemfreq(planar_mesh_faces[:,1])
        number_of_planar_surfaces = surface_flags.shape[0]

        E1 = [1.,0.,0.]
        E2 = [0.,1.,0.]
        E3 = [0.,0.,1.]

        # MAKE A SINGLE INSTANCE OF MATERIAL AND UPDATE IF NECESSARY
        import Florence.MaterialLibrary
        pmaterial_func = getattr(Florence.MaterialLibrary,material.mtype,None)
        pmaterial = pmaterial_func(2,E=material.E,nu=material.nu,E_A=material.E_A,G_A=material.G_A)
        
        print "The problem requires 2D analyses. Solving", number_of_planar_surfaces, "2D problems"
        for niter in range(number_of_planar_surfaces):
            
            pmesh = Mesh()
            pmesh.element_type = "tri"
            pmesh.elements = mesh.faces[planar_mesh_faces[planar_mesh_faces[:,1]==surface_flags[niter,0],0],:]
            pmesh.nelem = np.int64(surface_flags[niter,1])
            pmesh.GetBoundaryEdgesTri()
            unique_edges = np.unique(pmesh.edges)
            Dirichlet2D = np.zeros((unique_edges.shape[0],3))
            nodesDBC2D = np.zeros(unique_edges.shape[0])
            
            unique_elements, inv  = np.unique(pmesh.elements, return_inverse=True)
            aranger = np.arange(unique_elements.shape[0],dtype=np.uint64)
            pmesh.elements = aranger[inv].reshape(pmesh.elements.shape)

            # elements = np.zeros_like(pmesh.elements)
            # unique_elements = np.unique(pmesh.elements)
            # counter = 0
            # for i in unique_elements:
            #     elements[pmesh.elements==i] = counter
            #     counter += 1
            # pmesh.elements = elements

            counter = 0
            for i in unique_edges:
                # nodesDBC2D[counter] = whereEQ(nodesDBC,i)[0][0]
                nodesDBC2D[counter] = np.where(nodesDBC==i)[0][0]
                Dirichlet2D[counter,:] = Dirichlet[nodesDBC2D[counter],:]
                counter += 1
            nodesDBC2D = nodesDBC2D.astype(np.int64)

            temp_dict = []
            for i in nodesDBC[nodesDBC2D].flatten():
                temp_dict.append(np.where(unique_elements==i)[0][0])
            nodesDBC2D = np.array(temp_dict,copy=False)

            pmesh.points = mesh.points[unique_elements,:]

            one_element_coord = pmesh.points[pmesh.elements[0,:3],:]

            # FOR COORDINATE TRANSFORMATION
            AB = one_element_coord[0,:] - one_element_coord[1,:]
            AC = one_element_coord[0,:] - one_element_coord[2,:]

            normal = np.cross(AB,AC)
            unit_normal = normal/np.linalg.norm(normal)

            e1 = AB/np.linalg.norm(AB)
            e2 = np.cross(normal,AB)/np.linalg.norm(np.cross(normal,AB))
            e3 = unit_normal

            # TRANSFORMATION MATRIX
            Q = np.array([
                [np.einsum('i,i',e1,E1), np.einsum('i,i',e1,E2), np.einsum('i,i',e1,E3)],
                [np.einsum('i,i',e2,E1), np.einsum('i,i',e2,E2), np.einsum('i,i',e2,E3)],
                [np.einsum('i,i',e3,E1), np.einsum('i,i',e3,E2), np.einsum('i,i',e3,E3)]
                ])

            pmesh.points = np.dot(pmesh.points,Q.T)
            # assert np.allclose(pmesh.points[:,2],pmesh.points[0,2])
            # z_plane = pmesh.points[0,2]

            pmesh.points = pmesh.points[:,:2]

            Dirichlet2D = np.dot(Dirichlet2D,Q.T)
            Dirichlet2D = Dirichlet2D[:,:2]

            pmesh.edges = None
            pmesh.GetBoundaryEdgesTri()

            # DEEP COPY BY SUBCLASSING
            class MainData2D(MainData):
                ndim = pmaterial.ndim
                nvar = pmaterial.nvar
                __PARALLEL__ = False

            # FOR DYNAMICALLY PATCHED ITEMS
            pboundary_condition = BoundaryCondition()
            pboundary_condition.SetCADProjectionParameters()
            # pboundary_condition = pboundary_condition
            pboundary_condition.is_dirichlet_computed = True
            # MainData2D.BoundaryData.nodesDBC = nodesDBC2D
            # MainData2D.BoundaryData.Dirichlet = Dirichlet2D
            pboundary_condition.nodesDBC = nodesDBC2D[:,None]
            pboundary_condition.Dirichlet = Dirichlet2D
            # MainData2D.MeshInfo.MeshType = "tri"

            # COMPUTE BASES FOR TRIANGULAR ELEMENTS
            QuadratureOpt = 3   # OPTION FOR QUADRATURE TECHNIQUE FOR TRIS AND TETS
            norder = MainData.C+MainData.C
            if norder == 0:
                # TAKE CARE OF C=0 CASE
                norder = 1
            MainData2D.Domain, MainData2D.Boundary, MainData2D.Quadrature = GetBasesAtInegrationPoints(MainData2D.C,
                norder,QuadratureOpt,"tri")
            # SEPARATELY COMPUTE INTERPOLATION FUNCTIONS AT ALL INTEGRATION POINTS FOR POST-PROCESSING
            norder_post = (MainData.C+1)+(MainData.C+1)
            MainData2D.PostDomain, MainData2D.PostBoundary, MainData2D.PostQuadrature = GetBasesAtInegrationPoints(MainData2D.C,
                norder_post,QuadratureOpt,"tri")
            
            
            print 'Solvingq planar problem number', niter, 'Number of DoF is', pmesh.points.shape[0]*MainData2D.nvar
            if pmesh.points.shape[0] != Dirichlet2D.shape[0]:
                # CALL THE MAIN SOLVER FOR SOLVING THE 2D PROBLEM
                TotalDisp = MainSolver(MainData2D,pmesh,pmaterial,pboundary_condition)
            else:
                # IF THERE IS NO DEGREE OF FREEDOM TO SOLVE FOR (ONE ELEMENT CASE)
                TotalDisp = Dirichlet2D[:,:,None]

            Disp = np.zeros((TotalDisp.shape[0],3))
            Disp[:,:2] = TotalDisp[:,:,-1]

            temp_dict = []
            for i in unique_elements:
                temp_dict.append(np.where(nodesDBC==i)[0][0])

            Dirichlet[temp_dict,:] = np.dot(Disp,Q)

            if plot:
                PostProcess.HighOrderCurvedPatchPlot(pmesh,TotalDisp,QuantityToPlot=MainData2D.ScaledJacobian,InterpolationDegree=40)
                import matplotlib.pyplot as plt
                plt.show()

            del pmesh, pboundary_condition

        gc.collect()






    def GetReducedMatrices(self,stiffness,F,mass=None):

        # GET REDUCED FORCE VECTOR
        F_b = F[self.columns_in,0]

        # GET REDUCED STIFFNESS MATRIX
        stiffness_b = stiffness[self.columns_in,:][:,self.columns_in]

        # GET REDUCED MASS MATRIX
        mass_b = np.array([])
        if self.analysis_type != 'static':
            mass_b = mass[self.columns_in,:][:,self.columns_in]

        return stiffness_b, F_b, mass_b


    def ApplyDirichletGetReducedMatrices(self,stiffness,F,AppliedDirichlet,mass=None):
        """AppliedDirichlet is a non-member because it can be external incremental Dirichlet,
            which is currently not implemented as member of BoundaryCondition. F also does not 
            correspond to Dirichlet forces, as it can be residual in incrementally linearised
            framework.
        """

        # APPLY DIRICHLET BOUNDARY CONDITIONS
        for i in range(0,self.columns_out.shape[0]):
            F = F - AppliedDirichlet[i]*stiffness.getcol(self.columns_out[i])

        # for i in range(0,self.columns_out.shape[0]):
            # self.dirichlet_forces = self.dirichlet_forces - AppliedDirichlet[i]*stiffness.getcol(self.columns_out[i])

        # GET REDUCED FORCE VECTOR
        F_b = F[self.columns_in,0]
        # F_b = self.dirichlet_forces[self.columns_in,0]

        # print int(sp.__version__.split('.')[1] )
        # FOR UMFPACK SOLVER TAKE SPECIAL CARE
        if int(sp.__version__.split('.')[1]) < 15:
            F_b_umf = np.zeros(F_b.shape[0])
            # F_b_umf[:] = F_b[:,0] # DOESN'T WORK
            for i in range(F_b_umf.shape[0]):
                F_b_umf[i] = F_b[i,0]
            F_b = np.copy(F_b_umf)

        # GET REDUCED STIFFNESS
        stiffness_b = stiffness[self.columns_in,:][:,self.columns_in]

        # GET REDUCED MASS MATRIX
        if self.analysis_type != 'static':
            mass = mass[self.columns_in,:][:,self.columns_in]
            return stiffness_b, F_b, F, mass_b

        return stiffness_b, F_b, F



    def SetNURBSParameterisation(self,nurbs_func,*args):
        self.nurbs_info = nurbs_func(*args)
        

    def SetNURBSCondition(self,nurbs_func,*args):
        self.nurbs_condition = nurbs_func(*args)

    def NeumannCriterion(self,NeuArgs,Analysis=0,Step=0):
        pass


    def GetExternalForces(self,mesh,material):
        # FIND PURE NEUMANN (EXTERNAL) NODAL FORCE VECTOR
        # NeumannForces = AssemblyForces(MainData,mesh)
        # NeumannForces = AssemblyForces_Cheap(MainData,mesh)
        # NeumannForces = np.zeros((mesh.points.shape[0]*MainData.nvar,1),dtype=np.float64)
        # NeumannForces = np.zeros((mesh.points.shape[0]*MainData.nvar,1),dtype=np.float32)
        self.neumann_forces = np.zeros((mesh.points.shape[0]*material.nvar,1),dtype=np.float32)

        # FORCES RESULTING FROM DIRICHLET BOUNDARY CONDITIONS
        # DirichletForces = np.zeros((mesh.points.shape[0]*MainData.nvar,1),dtype=np.float64)
        # DirichletForces = np.zeros((mesh.points.shape[0]*MainData.nvar,1),dtype=np.float32)
        self.dirichlet_forces = np.zeros((mesh.points.shape[0]*material.nvar,1),dtype=np.float32)
