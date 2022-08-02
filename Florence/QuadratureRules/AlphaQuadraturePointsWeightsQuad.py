from __future__ import print_function
import numpy as np

def AlphaQuadraturePointsWeightsQuad(C):

    if C % 2 != 0:
        C += 1

    if C > 6:
        raise ValueError("Alpha optimal quadrature points beyond C=6 not available. Consider using tensor product or WV quadrature")

    if C == 0:
        zw = np.array([0., 0., 4.])
    elif C==2:
        zw = np.array([
            [-1.0, -1.0, 1.0],
            [ 1.0, -1.0, 1.0],
            [-1.0,  1.0, 1.0],
            [ 1.0,  1.0, 1.0]
            ])
    elif C==4:
        zw = np.array([
            [-1.0, -1.0, 0.111111111111111111111111111111111111],
            [ 0.0, -1.0, 0.444444444444444444444444444444444444],
            [ 1.0, -1.0, 0.111111111111111111111111111111111111],
            [-1.0,  0.0, 0.444444444444444444444444444444444444],
            [ 0.0,  0.0, 1.777777777777777777777777777777777777],
            [ 1.0,  0.0, 0.444444444444444444444444444444444444],
            [-1.0,  1.0, 0.111111111111111111111111111111111111],
            [ 0.0,  1.0, 0.444444444444444444444444444444444444],
            [ 1.0,  1.0, 0.111111111111111111111111111111111111]
        ])
    elif C==6:
        zw = np.array([
            [-1.0,                                        -1.0,                                    0.027777777777777777777777777777777777],
            [-0.447213595499957939281834733746255247,     -1.0,                                    0.138888888888888888888888888888888888],
            [ 0.447213595499957939281834733746255247,     -1.0,                                    0.138888888888888888888888888888888888],
            [ 1.0,                                        -1.0,                                    0.027777777777777777777777777777777777],
            [-1.0,                                        -0.447213595499957939281834733746255247, 0.138888888888888888888888888888888888],
            [-0.447213595499957939281834733746255247,     -0.447213595499957939281834733746255247, 0.694444444444444444444444444444444444],
            [ 0.447213595499957939281834733746255247,     -0.447213595499957939281834733746255247, 0.694444444444444444444444444444444444],
            [ 1.0,                                        -0.447213595499957939281834733746255247, 0.138888888888888888888888888888888888],
            [-1.0,                                         0.447213595499957939281834733746255247, 0.138888888888888888888888888888888888],
            [-0.447213595499957939281834733746255247,      0.447213595499957939281834733746255247, 0.694444444444444444444444444444444444],
            [ 0.447213595499957939281834733746255247,      0.447213595499957939281834733746255247, 0.694444444444444444444444444444444444],
            [ 1.0,                                         0.447213595499957939281834733746255247, 0.138888888888888888888888888888888888],
            [-1.0,                                         1.0,                                    0.027777777777777777777777777777777777],
            [-0.447213595499957939281834733746255247,      1.0,                                    0.138888888888888888888888888888888888],
            [ 0.447213595499957939281834733746255247,      1.0,                                    0.138888888888888888888888888888888888],
            [ 1.0,                                         1.0,                                    0.027777777777777777777777777777777777]
        ])

    return zw