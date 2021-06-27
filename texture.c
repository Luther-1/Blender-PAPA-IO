// The MIT License
// 
// Copyright (c) 2021        Marcus Der      marcusder@hotmail.com
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
void dxtDecodeColourMap( unsigned char* data, int dataLoc, float colours[4][3] ) { // [[R,G,B] * 4]
    unsigned int colour0 = (data[dataLoc+0]) | (data[dataLoc+1] << 8);
    unsigned int colour1 = (data[dataLoc+2]) | (data[dataLoc+3] << 8);

    colours[0][0] = (colour0>>8) & 0b11111000;
    colours[0][1] = (colour0>>3) & 0b11111100;
    colours[0][2] = (colour0<<3) & 0b11111000;

    colours[1][0] = (colour1>>8) & 0b11111000;
    colours[1][1] = (colour1>>3) & 0b11111100;
    colours[1][2] = (colour1<<3) & 0b11111000;

    if (colour0 > colour1) {
        colours[2][0] = (float)(2 * colours[0][0] + colours[1][0]) / 765.0;
        colours[2][1] = (float)(2 * colours[0][1] + colours[1][1]) / 765.0;
        colours[2][2] = (float)(2 * colours[0][2] + colours[1][2]) / 765.0;

        colours[3][0] = (float)(colours[0][0] + 2 * colours[1][0]) / 765.0;
        colours[3][1] = (float)(colours[0][1] + 2 * colours[1][1]) / 765.0;
        colours[3][2] = (float)(colours[0][2] + 2 * colours[1][2]) / 765.0;
    } else {
        colours[2][0] = (float)(colours[0][0] + colours[1][0]) / 510.0;
        colours[2][1] = (float)(colours[0][1] + colours[1][1]) / 510.0;
        colours[2][2] = (float)(colours[0][2] + colours[1][2]) / 510.0;

        colours[3][0] = 0.0;
        colours[3][1] = 0.0;
        colours[3][2] = 0.0;
        
    }

    colours[0][0] /= 255.0;
    colours[0][1] /= 255.0;
    colours[0][2] /= 255.0;

    colours[1][0] /= 255.0;
    colours[1][1] /= 255.0;
    colours[1][2] /= 255.0;
}

void dxtDecodeAlphaMap( unsigned char* data, int dataLoc, float alphaValues[16] ) {
    float alphaMap[8];
    alphaMap[0] = (float)data[dataLoc+0];
    alphaMap[1] = (float)data[dataLoc+1];

    if(alphaMap[0] > alphaMap[1]) {
        for(int i=1; i<7; i++) {
            alphaMap[i+1] = ((7-i) * alphaMap[0] + i * alphaMap[1]) / 7.0;
        }
    } else {
        for(int i=1; i<5; i++) {
            alphaMap[i+1] = ((5-i) * alphaMap[0] + i * alphaMap[1]) / 5.0;
        }
        alphaMap[6] = 0.0;
        alphaMap[7] = 255.0;
    }

    for(int i=0; i<8; i++) {
        alphaMap[i] /= 255.0;
    }

    unsigned long long alphaBits = 0;

    for(int i=2; i<8; i++) { // pack the rest of the data into a single long for easy access
        alphaBits |= ((unsigned long long) data[i+dataLoc]) << ((i-2) * 8);
    }

    for(int i=0; i<16; i++) {
        alphaValues[i] = alphaMap[alphaBits & 0b111];
        alphaBits>>=3;
    }
}

void decodeTexture( unsigned char* data, int width, int height, int format, float* dst ) {

    int heightZero = height - 1;

    if(format == 1) { // RGBA8888
        for(int y=0; y<height; y++) {
            for (int x = 0; x<width; x++) {
                int i = (x + (heightZero - y) * width) * 4;
                int i2 = (x + y * width) * 4;
                dst[i] = (float)data[i]/255.0;
                dst[i+1] = (float)data[i+1]/255.0;
                dst[i+2] = (float)data[i+2]/255.0;
                dst[i+3] = (float)data[i+3]/255.0;
            }
        }
    } else if(format == 2) { // RGBX8888
        for(int y=0; y<height; y++) {
            for (int x = 0; x<width; x++) {
                int i = (x + (heightZero - y) * width) * 4;
                int i2 = (x + y * width) * 4;
                dst[i] = (float)data[i2] / 255.0;
                dst[i+1] = (float)data[i2+1] / 255.0;
                dst[i+2] = (float)data[i2+2] / 255.0;
                dst[i+3] = (float)data[i2+3] / 255.0;
            }
        }
    } else if(format == 3) { // BGRA8888
        for(int y=0; y<height; y++) {
            for (int x = 0; x<width; x++) {
                int i = (x + (heightZero - y) * width) * 4;
                int i2 = (x + y * width) * 4;
                dst[i]=(float)data[i2]/255.0;
                dst[i+1]=(float)data[i2+1]/255.0;
                dst[i+2]=(float)data[i2+2]/255.0;
                dst[i+3]=(float)data[i2+3]/255.0;
                int t = dst[i];
                dst[i] = dst[i2+2];
                dst[i+2] = t;
            }
        }
    } else if (format==4) { // DXT1
        int bufferLoc = 0;
        float colours[4][3];
        for(int y=0; y<height; y+=4) {
            for(int x=0; x<width; x+=4) {

                dxtDecodeColourMap(data, bufferLoc, colours);
                bufferLoc+=4;

                long long bits = 0;
                bits |= data[bufferLoc++]<<0;
                bits |= data[bufferLoc++]<<8;
                bits |= data[bufferLoc++]<<16;
                bits |= data[bufferLoc++]<<24;

                for(int yy =0; yy<4; yy++) {
                    for(int xx =0; xx<4; xx++) { // copy our colour data into the array
                        unsigned int colourIndex = bits & 0b11;
                        if(yy+y < height && xx + y < width) {
                            int idx = (xx + x + (heightZero - (yy + y)) * width) * 4;
                            float* col = colours[colourIndex];
                            dst[idx] = col[0];
                            dst[idx+1] = col[1];
                            dst[idx+2] = col[2];
                            dst[idx+3] = 1.0;
                        }
                        bits>>=2;
                    }
                }
            }
        }
    } else if (format==6) { // DXT5
        int bufferLoc = 0;
        float alphaValues[16];
        float colours[4][3];
        for(int y=0; y<height; y+=4) {
            for(int x=0; x<width; x+=4) {

                dxtDecodeAlphaMap(data, bufferLoc, alphaValues);
                bufferLoc+=8;

                dxtDecodeColourMap(data, bufferLoc, colours);
                bufferLoc+=4;

                unsigned long long bits = 0;
                bits |= data[bufferLoc++]<<0;
                bits |= data[bufferLoc++]<<8;
                bits |= data[bufferLoc++]<<16;
                bits |= data[bufferLoc++]<<24;

                for(int yy=0; yy<4; yy++) {
                    for(int xx=0; xx<4; xx++) { // copy our colour data into the array
                        int colourIndex = bits & 0b11;
                        if(yy+y < height && xx + x < width) {
                            int idx = (xx + x + (heightZero - (yy + y)) * width) * 4;
                            float* col = colours[colourIndex];
                            dst[idx] = col[0];
                            dst[idx+1] = col[1];
                            dst[idx+2] = col[2];
                            dst[idx+3] = alphaValues[xx + yy * 4];
                        }
                        bits>>=2;
                    }
                }
            }
        }
    } else if (format == 13) {
        for(int y=0; y<height; y++) {
            for (int x = 0; x<width; x++) {
                int idx = x + (heightZero-y) * width * 4;
                int idx2 = x + y * width;
                dst[idx] = (float)data[idx2]/255.0; // R
                dst[idx+1] = 0.0; // G
                dst[idx+2] = 0.0; // B
                dst[idx+3] = 1.0; // A
            }
        }
    }
}
